"""Logging (Phase 5): line formats, request IDs, the access log, and Uvicorn's loggers.

No database needed. `configure_logging` changes loggers for the whole process, so a fixture
puts them back after each test.
"""

import asyncio
import io
import json
import logging
import re
import uuid
from collections.abc import Iterator
from typing import Any

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient
from starlette.types import Message, Receive, Scope, Send

from app.core.logs import (
    HANDLER_NAME,
    JsonFormatter,
    RequestIdFilter,
    TextFormatter,
    configure_logging,
    current_request_id,
)
from app.core.metrics import Metrics
from app.core.middleware import MAX_REQUEST_BODY_BYTES, NO_ROUTE, AccessLogMiddleware
from tests.conftest import AppFactory
from tests.support import CSRF_HEADERS, make_settings, sample_value

WEB_ORIGIN = "http://localhost:5173"
REQUEST_ID = "0123456789abcdef0123456789abcdef"
TIME = re.compile(r"\d{4}-\d\d-\d\dT\d\d:\d\d:\d\d\.\d{3}Z")


@pytest.fixture(autouse=True)
def restore_logging() -> Iterator[None]:
    root = logging.getLogger()
    root_level = root.level
    saved = [
        (logger, list(logger.handlers), logger.level, logger.propagate, logger.disabled)
        for logger in map(logging.getLogger, ("app", "uvicorn", "uvicorn.error", "uvicorn.access"))
    ]
    yield
    for handler in [handler for handler in root.handlers if handler.get_name() == HANDLER_NAME]:
        root.removeHandler(handler)
    root.setLevel(root_level)
    for logger, handlers, level, propagate, disabled in saved:
        logger.handlers[:] = handlers
        logger.setLevel(level)
        logger.propagate = propagate
        logger.disabled = disabled


def _logger_writing_to(stream: io.StringIO, formatter: logging.Formatter) -> logging.Logger:
    """A logger outside the logging tree, with a handler set up like configure_logging's."""
    handler = logging.StreamHandler(stream)
    handler.setFormatter(formatter)
    handler.addFilter(RequestIdFilter())
    logger = logging.Logger("tests.logs", logging.DEBUG)
    logger.addHandler(handler)
    return logger


def _lines(stream: io.StringIO, logger: str | None = None) -> list[dict[str, Any]]:
    lines = [json.loads(line) for line in stream.getvalue().splitlines()]
    return [line for line in lines if logger is None or line["logger"] == logger]


def test_json_lines_hold_the_request_id_and_no_unknown_extras() -> None:
    stream = io.StringIO()
    logger = _logger_writing_to(stream, JsonFormatter())

    token = current_request_id.set(REQUEST_ID)
    try:
        logger.info(
            "Indexed %d chunks",
            3,
            extra={
                "route": "/things/{thing_id}",
                "status": 200,
                "color_message": "Indexed \x1b[1m%d\x1b[0m chunks",
                "client_address": "203.0.113.9",
            },
        )
    finally:
        current_request_id.reset(token)

    line = json.loads(stream.getvalue())
    assert TIME.fullmatch(line.pop("time"))
    assert line == {
        "level": "INFO",
        "logger": "tests.logs",
        "message": "Indexed 3 chunks",
        "request_id": REQUEST_ID,
        "route": "/things/{thing_id}",
        "status": 200,
    }


def test_json_lines_keep_exceptions_on_the_same_line() -> None:
    stream = io.StringIO()
    logger = _logger_writing_to(stream, JsonFormatter())

    try:
        raise ValueError("synthetic failure")
    except ValueError:
        logger.exception("Something failed")

    [raw] = stream.getvalue().splitlines()
    line = json.loads(raw)
    assert (line["level"], line["message"], line["request_id"]) == (
        "ERROR",
        "Something failed",
        None,
    )
    assert line["exception"].startswith("Traceback (most recent call last):")
    assert line["exception"].endswith("ValueError: synthetic failure")


def test_text_lines_show_the_request_id_or_a_dash() -> None:
    stream = io.StringIO()
    logger = _logger_writing_to(stream, TextFormatter())

    logger.warning("Outside a request")
    token = current_request_id.set(REQUEST_ID)
    try:
        logger.warning("Inside a request")
    finally:
        current_request_id.reset(token)

    outside, inside = stream.getvalue().splitlines()
    assert outside.endswith(" WARNING tests.logs [-] Outside a request")
    assert inside.endswith(f" WARNING tests.logs [{REQUEST_ID}] Inside a request")


def test_the_app_logs_from_log_level_and_other_libraries_from_warning() -> None:
    stream = io.StringIO()
    configure_logging(make_settings(), stream=stream)

    logging.getLogger("app.example").info("App info")
    logging.getLogger("app.example").debug("App debug")
    logging.getLogger("tests.library").info("Library info")
    logging.getLogger("tests.library").warning("Library warning")

    output = stream.getvalue()
    assert "App info" in output
    assert "Library warning" in output
    assert "App debug" not in output
    assert "Library info" not in output


@pytest.mark.parametrize("level", ["debug", "DEBUG"])
def test_debug_level_shows_the_apps_debug_lines(level: str) -> None:
    stream = io.StringIO()
    configure_logging(make_settings(log_level=level), stream=stream)

    logging.getLogger("app.example").debug("Debug detail")

    assert "Debug detail" in stream.getvalue()


def test_warning_level_hides_the_apps_info_lines() -> None:
    stream = io.StringIO()
    configure_logging(make_settings(log_level="WARNING"), stream=stream)

    logging.getLogger("app.example").info("Routine")
    logging.getLogger("app.example").warning("Problem")

    assert "Routine" not in stream.getvalue()
    assert "Problem" in stream.getvalue()


def test_uvicorns_lines_are_written_once_and_its_access_log_is_off() -> None:
    # How Uvicorn's default logging configuration leaves its loggers.
    uvicorn_stream = io.StringIO()
    for name in ("uvicorn", "uvicorn.access"):
        server_logger = logging.getLogger(name)
        server_logger.handlers[:] = [logging.StreamHandler(uvicorn_stream)]
        server_logger.setLevel(logging.INFO)
        server_logger.propagate = False
    logging.getLogger("uvicorn.error").setLevel(logging.INFO)
    stream = io.StringIO()

    configure_logging(make_settings(), stream=stream)
    logging.getLogger("uvicorn.error").info("Application startup complete.")
    logging.getLogger("uvicorn.access").info(
        '%s - "%s %s HTTP/%s" %d',
        "203.0.113.9:50000",
        "GET",
        "/api/v1/auth/me?token=synthetic",
        "1.1",
        401,
    )

    [line] = stream.getvalue().splitlines()
    assert line.endswith(" INFO uvicorn.error [-] Application startup complete.")
    assert uvicorn_stream.getvalue() == ""
    # Uvicorn checks this, and skips its access log altogether when it's false.
    assert not logging.getLogger("uvicorn.access").hasHandlers()


def test_configuring_again_replaces_the_handler() -> None:
    first, second = io.StringIO(), io.StringIO()
    configure_logging(make_settings(), stream=first)
    configure_logging(make_settings(log_format="json"), stream=second)

    logging.getLogger("app.example").warning("Logged once")

    assert first.getvalue() == ""
    assert json.loads(second.getvalue())["message"] == "Logged once"
    names = [handler.get_name() for handler in logging.getLogger().handlers]
    assert names.count(HANDLER_NAME) == 1


@pytest.fixture
def logged_app(make_app: AppFactory) -> tuple[FastAPI, io.StringIO]:
    """An app whose logs go to a buffer, as JSON lines."""
    app = make_app(log_format="json")
    stream = io.StringIO()
    configure_logging(app.state.settings, stream=stream)
    return app, stream


def test_each_request_is_logged_once_with_its_route_and_request_id(
    logged_app: tuple[FastAPI, io.StringIO],
) -> None:
    app, stream = logged_app

    response = TestClient(app).get("/api/v1/auth/me?token=synthetic-query-secret")

    [line] = _lines(stream, "app.access")
    assert re.fullmatch(r"GET /api/v1/auth/me 401 \d+\.\d ms", line["message"])
    assert line["request_id"] == response.headers["X-Request-ID"]
    assert (line["level"], line["method"], line["route"], line["status"]) == (
        "INFO",
        "GET",
        "/api/v1/auth/me",
        401,
    )
    assert line["duration_ms"] >= 0
    assert "synthetic-query-secret" not in stream.getvalue()


def test_requests_are_named_by_route_template_never_by_path(
    logged_app: tuple[FastAPI, io.StringIO],
) -> None:
    app, stream = logged_app
    client = TestClient(app)
    workspace_id = str(uuid.uuid4())

    client.get(f"/api/v1/workspaces/{workspace_id}/documents")
    client.get("/api/v1/synthetic-unknown-page")

    lines = _lines(stream, "app.access")
    assert [(line["route"], line["status"]) for line in lines] == [
        ("/api/v1/workspaces/{workspace_id}/documents", 401),
        (NO_ROUTE, 404),
    ]
    assert workspace_id not in stream.getvalue()
    assert "synthetic-unknown-page" not in stream.getvalue()


def test_requests_answered_before_routing_name_the_route_they_were_for(
    logged_app: tuple[FastAPI, io.StringIO],
) -> None:
    app, stream = logged_app
    client = TestClient(app)

    preflight = client.options(
        "/api/v1/workspaces",
        headers={"Origin": WEB_ORIGIN, "Access-Control-Request-Method": "POST"},
    )
    too_large = client.post(
        "/api/v1/auth/login",
        content=b"x" * (MAX_REQUEST_BODY_BYTES + 1),
        headers={**CSRF_HEADERS, "Content-Type": "application/json"},
    )

    assert (preflight.status_code, too_large.status_code) == (200, 413)
    lines = _lines(stream, "app.access")
    assert [(line["method"], line["route"], line["status"]) for line in lines] == [
        ("OPTIONS", "/api/v1/workspaces", 200),
        ("POST", "/api/v1/auth/login", 413),
    ]


def test_lines_logged_in_worker_threads_carry_the_request_id(
    logged_app: tuple[FastAPI, io.StringIO],
) -> None:
    app, stream = logged_app

    # FastAPI runs handlers that aren't `async` in a pool of worker threads.
    def handler() -> dict[str, str]:
        logging.getLogger("app.tests").info("Inside the handler")
        return {}

    app.add_api_route("/tests/worker-thread", handler)
    response = TestClient(app).get("/tests/worker-thread")

    [inside] = [line for line in _lines(stream) if line["message"] == "Inside the handler"]
    assert inside["request_id"] == response.headers["X-Request-ID"]


def test_health_checks_and_scrapes_are_logged_only_at_debug(make_app: AppFactory) -> None:
    app = make_app(log_format="json", metrics_enabled=True)
    client = TestClient(app)
    stream = io.StringIO()

    configure_logging(app.state.settings, stream=stream)
    client.get("/health/live")
    client.get("/metrics")
    assert _lines(stream, "app.access") == []

    configure_logging(make_settings(log_format="json", log_level="DEBUG"), stream=stream)
    client.get("/health/live")
    client.get("/metrics")
    lines = _lines(stream, "app.access")
    assert [(line["level"], line["route"]) for line in lines] == [
        ("DEBUG", "/health/live"),
        ("DEBUG", "/metrics"),
    ]


def test_requests_that_get_no_response_are_logged_and_counted_as_such() -> None:
    stream = io.StringIO()
    configure_logging(make_settings(log_format="json"), stream=stream)
    metrics = Metrics()

    async def client_left(scope: Scope, receive: Receive, send: Send) -> None:
        return None

    async def failing(scope: Scope, receive: Receive, send: Send) -> None:
        raise RuntimeError("synthetic failure")

    async def receive() -> Message:
        return {"type": "http.disconnect"}

    async def send(message: Message) -> None:
        raise AssertionError("nothing should be sent")

    def scope() -> Scope:
        return {"type": "http", "method": "POST", "path": "/synthetic", "headers": []}

    asyncio.run(AccessLogMiddleware(client_left, metrics)(scope(), receive, send))
    with pytest.raises(RuntimeError, match="synthetic failure"):
        asyncio.run(AccessLogMiddleware(failing, metrics)(scope(), receive, send))

    lines = _lines(stream, "app.access")
    assert [(line["route"], line["status"]) for line in lines] == [(NO_ROUTE, None)] * 2
    for line in lines:
        assert re.fullmatch(r"POST \(no route\) no response \d+\.\d ms", line["message"])
    exposition = metrics.exposition("")[0].decode()
    labels = {"method": "POST", "route": NO_ROUTE, "status": "none"}
    assert sample_value(exposition, "http_requests_total", **labels) == 2
