"""The request body size limit (P5-04). No database needed.

The test client sends each body as one message, so most tests call the middleware directly
with a client that sends the body in parts.
"""

import json

import anyio
from fastapi.testclient import TestClient
from starlette.types import Message, Receive, Scope, Send

from app.core.middleware import MAX_REQUEST_BODY_BYTES, RequestBodyLimitMiddleware
from app.domain.questions import MAX_QUESTION_LENGTH
from tests.support import CSRF_HEADERS, error_code

LIMIT = 10
REQUEST_ID = "a-request-id"
WEB_ORIGIN = "http://localhost:5173"
DISCONNECT: Message = {"type": "http.disconnect"}


class BodyReadingApp:
    """Reads the whole body and the message after it, then answers 204."""

    def __init__(self) -> None:
        self.received: list[Message] = []

    async def __call__(self, scope: Scope, receive: Receive, send: Send) -> None:
        self.received.append(await receive())
        while self.received[-1].get("more_body", False):
            self.received.append(await receive())
        self.received.append(await receive())
        await send({"type": "http.response.start", "status": 204, "headers": []})
        await send({"type": "http.response.body", "body": b""})


def _part(body: bytes, *, more: bool) -> Message:
    return {"type": "http.request", "body": body, "more_body": more}


def _send_through_limit(
    messages: list[Message],
    *,
    path: str = "/api/v1/auth/login",
    headers: list[tuple[bytes, bytes]] | None = None,
) -> tuple[BodyReadingApp, list[Message]]:
    app = BodyReadingApp()
    middleware = RequestBodyLimitMiddleware(app, max_body_bytes=LIMIT)
    scope = {
        "type": "http",
        "method": "POST",
        "path": path,
        "headers": headers or [],
        "state": {"request_id": REQUEST_ID},
    }
    # Receiving more than the test provides fails the test.
    to_receive = list(messages)
    sent: list[Message] = []

    async def receive() -> Message:
        return to_receive.pop(0)

    async def send(message: Message) -> None:
        sent.append(message)

    anyio.run(middleware, scope, receive, send)
    return app, sent


def _assert_refused(sent: list[Message]) -> None:
    assert sent[0]["type"] == "http.response.start"
    assert sent[0]["status"] == 413
    assert json.loads(sent[1]["body"]) == {
        "error": {
            "code": "request_too_large",
            "message": "The request is too large.",
            "request_id": REQUEST_ID,
        }
    }


def test_a_body_within_the_limit_reaches_the_app_whole_and_once() -> None:
    app, sent = _send_through_limit(
        [_part(b"12345", more=True), _part(b"67890", more=False), DISCONNECT]
    )

    assert app.received == [_part(b"1234567890", more=False), DISCONNECT]
    assert sent[0]["status"] == 204


def test_a_body_over_the_limit_is_refused_before_the_app_sees_it() -> None:
    app, sent = _send_through_limit([_part(b"123456", more=True), _part(b"78901", more=True)])

    assert app.received == []
    _assert_refused(sent)


def test_a_declared_length_over_the_limit_is_refused_without_reading_the_body() -> None:
    app, sent = _send_through_limit([], headers=[(b"content-length", b"11")])

    assert app.received == []
    _assert_refused(sent)


def test_nothing_is_sent_to_a_client_that_disconnects() -> None:
    app, sent = _send_through_limit([_part(b"123", more=True), DISCONNECT])

    assert app.received == []
    assert sent == []


def test_uploads_are_left_to_their_own_limits() -> None:
    upload = _part(b"x" * (LIMIT + 1), more=False)

    app, sent = _send_through_limit([upload, DISCONNECT], path="/api/v1/workspaces/w1/documents")

    assert app.received == [upload, DISCONNECT]
    assert sent[0]["status"] == 204


def test_the_api_refuses_large_bodies_with_the_standard_error(make_app) -> None:
    client = TestClient(make_app())
    too_large = b"{" + b" " * MAX_REQUEST_BODY_BYTES + b"}"
    headers = {**CSRF_HEADERS, "Content-Type": "application/json", "Origin": WEB_ORIGIN}

    with_length = client.post("/api/v1/auth/login", content=too_large, headers=headers)
    # An iterator is sent in chunks, without a declared length.
    without_length = client.post("/api/v1/auth/login", content=iter([too_large]), headers=headers)

    for response in (with_length, without_length):
        assert response.status_code == 413
        assert error_code(response) == "request_too_large"
        assert response.json()["error"]["request_id"] == response.headers["X-Request-ID"]
        assert response.headers["Access-Control-Allow-Origin"] == WEB_ORIGIN


def test_the_longest_question_the_api_accepts_fits_within_the_limit() -> None:
    # JSON can spend at most 12 bytes on a character: an emoji escaped as two \uXXXX codes.
    body = json.dumps({"text": "\U0001f600" * 4 * MAX_QUESTION_LENGTH}).encode()

    assert len(body) < MAX_REQUEST_BODY_BYTES
