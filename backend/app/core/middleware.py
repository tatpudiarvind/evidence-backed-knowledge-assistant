import logging
import re
import uuid

from starlette.datastructures import Headers, MutableHeaders
from starlette.responses import JSONResponse
from starlette.types import ASGIApp, Message, Receive, Scope, Send

from app.core.errors import INTERNAL_ERROR_MESSAGE, error_content

REQUEST_ID_HEADER = "X-Request-ID"
# The largest request body read into memory. Every JSON body the API accepts fits, even with
# each character escaped.
MAX_REQUEST_BODY_BYTES = 64 * 1024
# Uploads stream to disk under their own size and time limits (D-33).
_UPLOAD_PATH = re.compile(r"/api/v1/workspaces/[^/]+/documents")

logger = logging.getLogger("app.errors")


class RequestIdMiddleware:
    """Gives every HTTP request a new random ID, returned in a header and in error bodies.

    Incoming request ID headers are ignored, so clients can't put arbitrary text in logs.
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

        await self.app(scope, receive, send_with_request_id)


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
                "Unhandled error (request_id=%s, method=%s, path=%s)",
                request_id,
                scope.get("method"),
                scope.get("path"),
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
