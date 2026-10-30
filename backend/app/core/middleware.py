import logging
import re
import time
import uuid

from fastapi.routing import RouteContext, iter_route_contexts
from starlette.datastructures import Headers, MutableHeaders
from starlette.responses import JSONResponse
from starlette.routing import Match
from starlette.types import ASGIApp, Message, Receive, Scope, Send

from app.core.errors import INTERNAL_ERROR_MESSAGE, error_content
from app.core.logs import current_request_id
from app.core.metrics import Metrics

REQUEST_ID_HEADER = "X-Request-ID"
# The largest request body read into memory. Every JSON body the API accepts fits, even with
# each character escaped.
MAX_REQUEST_BODY_BYTES = 64 * 1024
# Uploads stream to disk under their own size and time limits (D-33).
_UPLOAD_PATH = re.compile(r"/api/v1/workspaces/[^/]+/documents")
# How the access log and the metrics name a request whose path matches no route.
NO_ROUTE = "(no route)"
# Health checks and metric scrapes come often, so their requests are logged only at DEBUG.
_QUIET_ROUTES = frozenset({"/health/live", "/health/ready", "/metrics"})
# Other methods are logged and counted as OTHER, so clients can't add label values at will.
_KNOWN_METHODS = frozenset({"GET", "HEAD", "POST", "PUT", "PATCH", "DELETE", "OPTIONS"})

logger = logging.getLogger("app.errors")
access_logger = logging.getLogger("app.access")


class RequestIdMiddleware:
    """Gives every HTTP request a new random ID, returned in a header and in error bodies.

    The ID is also current while the request is handled, so log lines carry it. Incoming
    request ID headers are ignored, so clients can't put arbitrary text in logs.
    """

    def __init__(self, app: ASGIApp) -> None:
        self.app = app

    async def __call__(self, scope: Scope, receive: Receive, send: Send) -> None:
        if scope["type"] != "http":
            await self.app(scope, receive, send)
            return

        request_id = uuid.uuid4().hex
        scope.setdefault("state", {})["request_id"] = request_id

        async def send_with_request_id(message: Message) -> None:
            if message["type"] == "http.response.start":
                MutableHeaders(scope=message)[REQUEST_ID_HEADER] = request_id
            await send(message)

        token = current_request_id.set(request_id)
        try:
            await self.app(scope, receive, send_with_request_id)
        finally:
            current_request_id.reset(token)


class AccessLogMiddleware:
    """Logs one line per request, and counts it in the metrics.

    A request is named by its method and its route's template, such as
    `GET /api/v1/workspaces/{workspace_id}/documents`, so neither the lines nor the metrics
    hold IDs, query strings, or anything else a client puts in a URL. Client addresses are
    left out too.
    """

    def __init__(self, app: ASGIApp, metrics: Metrics) -> None:
        self.app = app
        self.metrics = metrics

    async def __call__(self, scope: Scope, receive: Receive, send: Send) -> None:
        if scope["type"] != "http":
            await self.app(scope, receive, send)
            return

        started = time.perf_counter()
        method = scope["method"] if scope["method"] in _KNOWN_METHODS else "OTHER"
        route = route_template(scope)
        status: int | None = None

        async def send_tracking_status(message: Message) -> None:
            nonlocal status
            if message["type"] == "http.response.start":
                status = message["status"]
            await send(message)

        try:
            await self.app(scope, receive, send_tracking_status)
        finally:
            seconds = time.perf_counter() - started
            self.metrics.count_request(method, route, status, seconds)
            access_logger.log(
                logging.DEBUG if route in _QUIET_ROUTES else logging.INFO,
                "%s %s %s %.1f ms",
                method,
                route,
                "no response" if status is None else status,
                seconds * 1000,
                extra={
                    "method": method,
                    "route": route,
                    "status": status,
                    "duration_ms": round(seconds * 1000, 1),
                },
            )


def route_template(scope: Scope) -> str:
    """The template of the route a request is for, such as `/api/v1/workspaces/{workspace_id}`.

    The route is found the way the router finds it: the first one that takes the request's
    method, or else the first one with its path. So requests answered before routing, such as
    CORS preflights and oversized bodies, are named too. FastAPI's `scope["route"]` isn't used:
    for a route from an included router, its path lacks the router's prefix.
    """
    routes = getattr(getattr(scope.get("app"), "router", None), "routes", None)
    same_path: str | None = None
    for route in iter_route_contexts(routes or ()):
        match, _ = route.matches(scope)
        if match is Match.FULL:
            return _path_template(route)
        if match is Match.PARTIAL and same_path is None:
            same_path = _path_template(route)
    return same_path or NO_ROUTE


def _path_template(route: RouteContext) -> str:
    path = route.path_format or route.path
    return path if isinstance(path, str) else NO_ROUTE


class UnhandledErrorMiddleware:
    """Turns unexpected exceptions into the standard error JSON.

    It runs inside the CORS middleware, so browsers can still read the error and its request ID.
    """

    def __init__(self, app: ASGIApp) -> None:
        self.app = app

    async def __call__(self, scope: Scope, receive: Receive, send: Send) -> None:
        if scope["type"] != "http":
            await self.app(scope, receive, send)
            return

        response_started = False

        async def send_tracking_start(message: Message) -> None:
            nonlocal response_started
            if message["type"] == "http.response.start":
                response_started = True
            await send(message)

        try:
            await self.app(scope, receive, send_tracking_start)
        except Exception:
            request_id = scope.get("state", {}).get("request_id")
            logger.exception(
                "Unhandled error (request_id=%s, method=%s, route=%s)",
                request_id,
                scope.get("method"),
                route_template(scope),
            )
            if response_started:
                raise
            response = JSONResponse(
                status_code=500,
                content=error_content("internal_error", INTERNAL_ERROR_MESSAGE, request_id),
            )
            await response(scope, receive, send)


class RequestBodyLimitMiddleware:
    """Refuses request bodies over a size limit before the app reads them.

    FastAPI reads a JSON body whole before validating it, so without this a client could make
    the API hold any amount of data in memory. Uploads are left to their own limits.
    """

    def __init__(self, app: ASGIApp, max_body_bytes: int = MAX_REQUEST_BODY_BYTES) -> None:
        self.app = app
        self.max_body_bytes = max_body_bytes

    async def __call__(self, scope: Scope, receive: Receive, send: Send) -> None:
        if scope["type"] != "http" or (
            scope["method"] == "POST" and _UPLOAD_PATH.fullmatch(scope["path"])
        ):
            await self.app(scope, receive, send)
            return

        declared_length = Headers(scope=scope).get("content-length", "")
        if declared_length.isdigit() and int(declared_length) > self.max_body_bytes:
            await self._refuse(scope, receive, send)
            return

        chunks: list[bytes] = []
        size = 0
        more_body = True
        while more_body:
            message = await receive()
            if message["type"] == "http.disconnect":
                # The client is gone, so there's no one to answer.
                return
            chunk: bytes = message.get("body", b"")
            size += len(chunk)
            if size > self.max_body_bytes:
                await self._refuse(scope, receive, send)
                return
            chunks.append(chunk)
            more_body = message.get("more_body", False)

        body_replayed = False

        async def replay_body() -> Message:
            nonlocal body_replayed
            if body_replayed:
                return await receive()
            body_replayed = True
            return {"type": "http.request", "body": b"".join(chunks), "more_body": False}

        await self.app(scope, replay_body, send)

    async def _refuse(self, scope: Scope, receive: Receive, send: Send) -> None:
        request_id = scope.get("state", {}).get("request_id")
        response = JSONResponse(
            status_code=413,
            content=error_content("request_too_large", "The request is too large.", request_id),
        )
        await response(scope, receive, send)
