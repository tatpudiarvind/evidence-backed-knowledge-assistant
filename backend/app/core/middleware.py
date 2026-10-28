import logging
import uuid

from starlette.datastructures import MutableHeaders
from starlette.responses import JSONResponse
from starlette.types import ASGIApp, Message, Receive, Scope, Send

from app.core.errors import INTERNAL_ERROR_MESSAGE, error_content

REQUEST_ID_HEADER = "X-Request-ID"

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
