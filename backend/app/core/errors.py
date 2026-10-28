"""The API's error contract: every error is JSON with a stable code, a safe message, and the
request ID. Stack traces, configuration, and submitted values are never echoed back."""

from typing import Any

from fastapi import FastAPI, Request
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse
from starlette.exceptions import HTTPException as StarletteHTTPException

INTERNAL_ERROR_MESSAGE = (
    "Something went wrong on the server. Try again; if it keeps happening, report the request ID."
)

_HTTP_ERRORS: dict[int, tuple[str, str]] = {
    400: ("bad_request", "The request could not be processed."),
    401: ("not_authenticated", "Sign in to continue."),
    403: ("forbidden", "You don't have access to this."),
    404: ("not_found", "Nothing was found at this address."),
    405: ("method_not_allowed", "This method isn't allowed here."),
    413: ("request_too_large", "The request is too large."),
    415: ("unsupported_media_type", "This content type isn't supported."),
}


class AppError(Exception):
    """An expected failure whose code and message are safe to show to users."""

    def __init__(
        self,
        status_code: int,
        code: str,
        message: str,
        *,
        headers: dict[str, str] | None = None,
    ) -> None:
        super().__init__(message)
        self.status_code = status_code
        self.code = code
        self.message = message
        self.headers = headers


def error_content(
    code: str,
    message: str,
    request_id: str | None,
    fields: list[dict[str, str]] | None = None,
) -> dict[str, Any]:
    error: dict[str, Any] = {"code": code, "message": message, "request_id": request_id}
    if fields:
        error["fields"] = fields
    return {"error": error}


def get_request_id(request: Request) -> str | None:
    request_id = getattr(request.state, "request_id", None)
    return request_id if isinstance(request_id, str) else None


def error_response(
    request: Request,
    status_code: int,
    code: str,
    message: str,
    *,
    headers: dict[str, str] | None = None,
    fields: list[dict[str, str]] | None = None,
) -> JSONResponse:
    return JSONResponse(
        status_code=status_code,
        content=error_content(code, message, get_request_id(request), fields),
        headers=headers,
    )


async def _handle_app_error(request: Request, exc: Exception) -> JSONResponse:
    if not isinstance(exc, AppError):
        raise exc
    return error_response(request, exc.status_code, exc.code, exc.message, headers=exc.headers)


async def _handle_validation_error(request: Request, exc: Exception) -> JSONResponse:
    if not isinstance(exc, RequestValidationError):
        raise exc
    fields = []
    for problem in exc.errors():
        # Only the location and message are returned; the submitted value ("input") never is.
        message = str(problem.get("msg", "Invalid value."))
        context = problem.get("ctx") or {}
        if problem.get("type") == "value_error" and "error" in context:
            message = str(context["error"])
        location = ".".join(str(part) for part in problem.get("loc", ()))
        fields.append({"location": location, "message": message})
    return error_response(
        request,
        422,
        "validation_failed",
        "Some fields are missing or invalid.",
        fields=fields,
    )


async def _handle_http_error(request: Request, exc: Exception) -> JSONResponse:
    if not isinstance(exc, StarletteHTTPException):
        raise exc
    code, message = _HTTP_ERRORS.get(
        exc.status_code, ("http_error", "The request could not be processed.")
    )
    headers = dict(exc.headers) if exc.headers else None
    return error_response(request, exc.status_code, code, message, headers=headers)


def register_error_handlers(app: FastAPI) -> None:
    app.add_exception_handler(AppError, _handle_app_error)
    app.add_exception_handler(RequestValidationError, _handle_validation_error)
    app.add_exception_handler(StarletteHTTPException, _handle_http_error)
