"""The Ollama adapter (P4-04), against a stand-in server on a free local port, and how the app
picks its language model."""

import json
import logging
import socket
import threading
from collections.abc import Iterator
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from typing import Any

import pytest

from app.core.config import MAX_ANSWER_TOKENS
from app.domain.grounding import ChatMessage
from app.providers.llm import (
    Generation,
    LanguageModelUnavailableError,
    OllamaChatModel,
    strip_thinking,
)
from tests.conftest import AppFactory
from tests.support import ScriptedLanguageModel, make_settings

MODEL = "synthetic-model:latest"
MESSAGES = [
    ChatMessage("system", "Synthetic rules."),
    ChatMessage("user", "Synthetic secret question about project records?"),
]


def reply_body(content: Any) -> bytes:
    return json.dumps(
        {"model": MODEL, "message": {"role": "assistant", "content": content}}
    ).encode()


class OllamaStub:
    """A stand-in Ollama server that gives every request the same response, and records them.

    With `hold` set, it doesn't respond until the test ends, like a model that's still thinking.
    """

    def __init__(self) -> None:
        self.status = 200
        self.body = reply_body("Records are kept for seven years [S1].")
        self.hold = False
        self.requests: list[tuple[str, str, dict[str, Any]]] = []
        self._released = threading.Event()
        stub = self

        class Handler(BaseHTTPRequestHandler):
            def do_POST(self) -> None:
                length = int(self.headers["Content-Length"])
                body = json.loads(self.rfile.read(length))
                stub.requests.append((self.path, self.headers["Content-Type"], body))
                if stub.hold:
                    stub._released.wait(30)
                    return
                self.send_response(stub.status)
                self.send_header("Content-Type", "application/json")
                self.send_header("Content-Length", str(len(stub.body)))
                self.end_headers()
                self.wfile.write(stub.body)

            def log_message(self, format: str, *args: Any) -> None:
                pass

        self._server = ThreadingHTTPServer(("127.0.0.1", 0), Handler)
        self.url = f"http://127.0.0.1:{self._server.server_address[1]}"
        self._thread = threading.Thread(target=self._server.serve_forever, daemon=True)
        self._thread.start()

    def close(self) -> None:
        self._released.set()
        self._server.shutdown()
        self._server.server_close()


@pytest.fixture
def ollama() -> Iterator[OllamaStub]:
    stub = OllamaStub()
    yield stub
    stub.close()


def chat_model(url: str, **overrides: Any) -> OllamaChatModel:
    settings = make_settings(
        llm_provider="ollama", ollama_base_url=url, ollama_model=MODEL, **overrides
    )
    return OllamaChatModel(settings)


def free_port() -> int:
    """A local port that nothing listens on: the system picked it, and it was closed again."""
    with socket.socket() as probe:
        probe.bind(("127.0.0.1", 0))
        port: int = probe.getsockname()[1]
    return port


def test_replies_come_from_the_chat_api_without_tools(ollama: OllamaStub) -> None:
    generation = chat_model(f"{ollama.url}/", ollama_context_tokens=8192).generate(MESSAGES)

    assert generation == Generation("Records are kept for seven years [S1].", MODEL)
    [(path, content_type, body)] = ollama.requests
    assert (path, content_type) == ("/api/chat", "application/json")
    assert body == {
        "model": MODEL,
        "messages": [
            {"role": "system", "content": "Synthetic rules."},
            {"role": "user", "content": "Synthetic secret question about project records?"},
        ],
        "stream": False,
        "options": {"temperature": 0, "num_ctx": 8192, "num_predict": MAX_ANSWER_TOKENS},
    }


def test_the_model_is_named_after_the_setting(ollama: OllamaStub) -> None:
    assert chat_model(ollama.url).name == MODEL


def test_reasoning_written_before_the_reply_is_removed(ollama: OllamaStub) -> None:
    ollama.body = reply_body("<think>\nSynthetic reasoning.\n</think>\n\n Kept [S1]. ")

    assert chat_model(ollama.url).generate(MESSAGES).text == "Kept [S1]."


@pytest.mark.parametrize(
    ("content", "reply"),
    [
        ("  Plain reply [S1].  ", "Plain reply [S1]."),
        ("<think>a</think>Reply", "Reply"),
        ("<think>a</think>Draft</think> Reply", "Reply"),
        ("<think>Still reasoning when it ran out of room", ""),
    ],
)
def test_strip_thinking(content: str, reply: str) -> None:
    assert strip_thinking(content) == reply


@pytest.mark.parametrize("status", [404, 500])
def test_error_responses_make_the_model_unavailable(
    ollama: OllamaStub, status: int, caplog: pytest.LogCaptureFixture
) -> None:
    ollama.status = status
    ollama.body = json.dumps({"error": f"model '{MODEL}' not found"}).encode()

    with pytest.raises(LanguageModelUnavailableError):
        chat_model(ollama.url).generate(MESSAGES)

    assert f"Ollama answered HTTP {status}" in caplog.text


@pytest.mark.parametrize(
    "body",
    [
        b"Synthetic text that isn't JSON",
        b"[]",
        b"{}",
        b'{"message": null}',
        b'{"message": {"role": "assistant"}}',
        reply_body(7),
    ],
)
def test_responses_that_are_not_ollama_replies_make_the_model_unavailable(
    ollama: OllamaStub, body: bytes
) -> None:
    ollama.body = body

    with pytest.raises(LanguageModelUnavailableError):
        chat_model(ollama.url).generate(MESSAGES)


@pytest.mark.parametrize("content", ["", " \n ", "<think>Synthetic unfinished reasoning"])
def test_empty_replies_make_the_model_unavailable(
    ollama: OllamaStub, content: str, caplog: pytest.LogCaptureFixture
) -> None:
    ollama.body = reply_body(content)

    with pytest.raises(LanguageModelUnavailableError):
        chat_model(ollama.url).generate(MESSAGES)

    assert "gave an empty reply" in caplog.text


def test_oversized_responses_make_the_model_unavailable(ollama: OllamaStub) -> None:
    ollama.body = reply_body("x" * (1024 * 1024))

    with pytest.raises(LanguageModelUnavailableError):
        chat_model(ollama.url).generate(MESSAGES)


def test_a_stopped_server_makes_the_model_unavailable(caplog: pytest.LogCaptureFixture) -> None:
    with pytest.raises(LanguageModelUnavailableError):
        chat_model(f"http://127.0.0.1:{free_port()}").generate(MESSAGES)

    assert f"Model {MODEL} is unavailable (URLError)" in caplog.text


def test_a_model_that_takes_too_long_is_unavailable(
    ollama: OllamaStub, caplog: pytest.LogCaptureFixture
) -> None:
    ollama.hold = True

    with pytest.raises(LanguageModelUnavailableError):
        chat_model(ollama.url, llm_timeout_seconds=1).generate(MESSAGES)

    assert "TimeoutError" in caplog.text


def test_proxy_settings_in_the_environment_are_ignored(
    ollama: OllamaStub, monkeypatch: pytest.MonkeyPatch
) -> None:
    # Port 9 (discard) refuses connections, so a request sent through this proxy would fail.
    monkeypatch.setenv("HTTP_PROXY", "http://127.0.0.1:9")
    monkeypatch.delenv("NO_PROXY", raising=False)
    monkeypatch.delenv("no_proxy", raising=False)

    assert chat_model(ollama.url).generate(MESSAGES).text.endswith("[S1].")
    assert len(ollama.requests) == 1


def test_logs_never_include_the_prompt_or_the_reply(
    ollama: OllamaStub, caplog: pytest.LogCaptureFixture
) -> None:
    caplog.set_level(logging.INFO)
    ollama.body = reply_body("Synthetic secret reply [S1].")
    chat_model(ollama.url).generate(MESSAGES)
    ollama.status = 500
    with pytest.raises(LanguageModelUnavailableError):
        chat_model(ollama.url).generate(MESSAGES)

    assert f"Model {MODEL} replied in" in caplog.text
    assert "secret" not in caplog.text


def test_apps_use_ollama_only_when_configured(make_app: AppFactory) -> None:
    assert isinstance(make_app(llm_provider="ollama").state.language_model, OllamaChatModel)
    assert make_app(llm_provider="none").state.language_model is None

    given = ScriptedLanguageModel()
    assert make_app(llm_provider="ollama", language_model=given).state.language_model is given
