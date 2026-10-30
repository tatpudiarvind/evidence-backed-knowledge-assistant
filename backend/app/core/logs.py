"""Logging (Phase 5): one line per event, as text or JSON, tagged with its request's ID.

Log calls name things by ID and count them. They never include secrets, document text, or the
text of questions and answers.
"""

import json
import logging
import sys
from contextvars import ContextVar
from datetime import UTC, datetime
from typing import Any, TextIO

from app.core.config import Settings

# The ID of the HTTP request being handled, if any. RequestIdMiddleware sets it.
current_request_id: ContextVar[str | None] = ContextVar("current_request_id", default=None)

# The only attributes JSON lines take from a record besides the standard ones. Libraries attach
# others, such as Uvicorn's colored copy of each message.
EXTRA_FIELDS = ("method", "route", "status", "duration_ms")
# Names the handler that configure_logging adds, so calling it again replaces that handler.
HANDLER_NAME = "knowledge-assistant"


class RequestIdFilter(logging.Filter):
    """Adds the current request's ID to each record logged while that request is handled."""

    def filter(self, record: logging.LogRecord) -> bool:
        request_id = current_request_id.get()
        if request_id is not None and not hasattr(record, "request_id"):
            record.request_id = request_id
        return True


class TextFormatter(logging.Formatter):
    """`time level logger [request ID] message`, with `-` outside requests."""

    def __init__(self) -> None:
        super().__init__(
            "%(asctime)s %(levelname)s %(name)s [%(request_id)s] %(message)s",
            defaults={"request_id": "-"},
        )


class JsonFormatter(logging.Formatter):
    """One JSON object per line, timed in UTC, with any exception on the same line."""

    def format(self, record: logging.LogRecord) -> str:
        time = datetime.fromtimestamp(record.created, UTC).isoformat(timespec="milliseconds")
        line: dict[str, Any] = {
            "time": time.replace("+00:00", "Z"),
            "level": record.levelname,
            "logger": record.name,
            "message": record.getMessage(),
            "request_id": getattr(record, "request_id", None),
        }
        for field in EXTRA_FIELDS:
            if field in record.__dict__:
                line[field] = record.__dict__[field]
        if record.exc_info:
            line["exception"] = self.formatException(record.exc_info)
        if record.stack_info:
            line["stack"] = self.formatStack(record.stack_info)
        return json.dumps(line, default=str)


def configure_logging(settings: Settings, stream: TextIO | None = None) -> logging.Handler:
    """Send the app's and Uvicorn's logs to one stream, standard error by default.

    The app's loggers log at LOG_LEVEL, other libraries' at WARNING and above. Uvicorn's access
    log is turned off: it records client addresses and whole URLs, query strings included,
    while AccessLogMiddleware logs each request by its route instead. Calling this again
    replaces the handler it added before.
    """
    handler = logging.StreamHandler(stream if stream is not None else sys.stderr)
    handler.set_name(HANDLER_NAME)
    handler.setFormatter(JsonFormatter() if settings.log_format == "json" else TextFormatter())
    handler.addFilter(RequestIdFilter())

    root = logging.getLogger()
    for previous in [existing for existing in root.handlers if existing.get_name() == HANDLER_NAME]:
        root.removeHandler(previous)
    root.addHandler(handler)
    root.setLevel(logging.WARNING)
    logging.getLogger("app").setLevel(settings.log_level)

    # Uvicorn's own messages, such as its startup lines, keep the levels Uvicorn gave them.
    for name in ("uvicorn", "uvicorn.error"):
        server_logger = logging.getLogger(name)
        server_logger.handlers.clear()
        server_logger.propagate = True
    access_logger = logging.getLogger("uvicorn.access")
    access_logger.handlers.clear()
    access_logger.propagate = False
    access_logger.disabled = True
    return handler
