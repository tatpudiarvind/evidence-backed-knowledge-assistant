"""The OpenAI-compatible adapter (P9-04), against a stand-in server on a free local port. No key
and no network are needed, and nothing here calls a hosted provider."""

import json
import logging
import threading
from collections.abc import Iterator
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from typing import Any

import pytest
from pydantic import ValidationError

from app.domain.grounding import ChatMessage
from app.providers.llm import (
    LanguageModelUnavailableError,
    OllamaChatModel,
    OpenAICompatibleChatModel,
    provider_of,
    sends_text_off_device,
)
from tests.support import make_settings

KEY = "synthetic-key-0123456789"
QUESTION = "Synthetic secret question about project records?"
MESSAGES = [ChatMessage("system", "Synthetic rules."), ChatMessage("user", QUESTION)]


def completion(content: Any = "Records are kept for seven years [S1].", **extra: Any) -> bytes:
    body = {"choices": [{"message": {"role": "assistant", "content": content}}], **extra}
    return json.dumps(body).encode()


class Stub:
    """Answers each request with the next scripted (status, headers, body), the last one
    repeating, and records the requests."""

    def __init__(self, *script: tuple[int, dict[str, str], bytes]) -> None:
        self.script = list(script) or [(200, {}, completion())]
        self.requests: list[tuple[str, dict[str, str], dict[str, Any]]] = []
        stub = self

        class Handler(BaseHTTPRequestHandler):
            def do_POST(self) -> None:
                length = int(self.headers["Content-Length"])
                body = json.loads(self.rfile.read(length))
                stub.requests.append((self.path, dict(self.headers), body))
                index = min(len(stub.requests), len(stub.script)) - 1
                status, headers, payload = stub.script[index]
                self.send_response(status)
                for name, value in headers.items():
                    self.send_header(name, value)
                self.send_header("Content-Length", str(len(payload)))
                self.end_headers()
                self.wfile.write(payload)

            def log_message(self, format: str, *args: Any) -> None:
                pass

        self._server = ThreadingHTTPServer(("127.0.0.1", 0), Handler)
        self.url = f"http://127.0.0.1:{self._server.server_address[1]}/v1"
        threading.Thread(target=self._server.serve_forever, daemon=True).start()

    def close(self) -> None:
        self._server.shutdown()
        self._server.server_close()


@pytest.fixture
def make_stub() -> Iterator[Any]:
    stubs: list[Stub] = []

    def make(*script: tuple[int, dict[str, str], bytes]) -> Stub:
        stubs.append(Stub(*script))
        return stubs[-1]

    yield make
    for stub in stubs:
        stub.close()


def model_for(stub: Stub, sleeps: list[float] | None = None, **overrides: Any) -> Any:
    settings = make_settings(
        llm_provider="openai_compatible",
        llm_base_url=stub.url,
        llm_model="synthetic-model",
        llm_api_key=KEY,
        **overrides,
    )
    recorded = sleeps if sleeps is not None else []
    return OpenAICompatibleChatModel(settings, sleep=recorded.append, random_fraction=lambda: 0.0)


def test_a_reply_is_read_with_its_token_counts(make_stub: Any) -> None:
    stub = make_stub((200, {}, completion(usage={"prompt_tokens": 120, "completion_tokens": 9})))
    generation = model_for(stub).generate(MESSAGES)

    assert generation.text == "Records are kept for seven years [S1]."
    assert generation.model_name == "synthetic-model"
    assert (generation.prompt_tokens, generation.completion_tokens) == (120, 9)
    path, headers, body = stub.requests[0]
    assert path == "/v1/chat/completions"
    assert headers["Authorization"] == f"Bearer {KEY}"
    assert body["model"] == "synthetic-model"
    assert body["temperature"] == 0
    assert body["stream"] is False
    assert "max_tokens" in body
    assert "tools" not in body
    assert [message["role"] for message in body["messages"]] == ["system", "user"]


def test_the_token_limit_parameter_can_be_changed(make_stub: Any) -> None:
    stub = make_stub()
    model_for(stub, llm_token_limit_parameter="max_completion_tokens").generate(MESSAGES)

    body = stub.requests[0][2]
    assert "max_completion_tokens" in body
    assert "max_tokens" not in body


def test_missing_token_counts_are_none(make_stub: Any) -> None:
    generation = model_for(make_stub()).generate(MESSAGES)
    assert generation.prompt_tokens is None
    assert generation.completion_tokens is None


def test_thinking_is_removed(make_stub: Any) -> None:
    stub = make_stub((200, {}, completion("<think>hmm</think>Seven years [S1].")))
    assert model_for(stub).generate(MESSAGES).text == "Seven years [S1]."


def test_a_busy_server_is_retried_after_the_wait_it_asks_for(make_stub: Any) -> None:
    stub = make_stub((429, {"Retry-After": "7"}, b"{}"), (200, {}, completion()))
    sleeps: list[float] = []

    assert model_for(stub, sleeps).generate(MESSAGES).text
    assert sleeps == [7.0]
    assert len(stub.requests) == 2


def test_a_long_retry_after_is_capped(make_stub: Any) -> None:
    stub = make_stub((429, {"Retry-After": "3600"}, b"{}"), (200, {}, completion()))
    sleeps: list[float] = []
    model_for(stub, sleeps).generate(MESSAGES)
    assert sleeps == [30.0]


def test_server_errors_back_off_and_then_give_up(make_stub: Any) -> None:
    stub = make_stub((503, {}, b"{}"))
    sleeps: list[float] = []

    with pytest.raises(LanguageModelUnavailableError):
        model_for(stub, sleeps, llm_max_retries=2).generate(MESSAGES)
    assert len(stub.requests) == 3
    assert sleeps == [1.0, 2.0]


def test_no_retries_means_one_try(make_stub: Any) -> None:
    stub = make_stub((500, {}, b"{}"))
    with pytest.raises(LanguageModelUnavailableError):
        model_for(stub, llm_max_retries=0).generate(MESSAGES)
    assert len(stub.requests) == 1


@pytest.mark.parametrize("status", [400, 401, 403, 404])
def test_other_client_errors_are_not_retried(make_stub: Any, status: int) -> None:
    stub = make_stub((status, {}, b"{}"))
    with pytest.raises(LanguageModelUnavailableError):
        model_for(stub).generate(MESSAGES)
    assert len(stub.requests) == 1


def test_a_redirect_is_not_followed(make_stub: Any) -> None:
    stub = make_stub((302, {"Location": "http://127.0.0.1:9/elsewhere"}, b""))
    with pytest.raises(LanguageModelUnavailableError):
        model_for(stub).generate(MESSAGES)
    assert len(stub.requests) == 1


@pytest.mark.parametrize(
    "body",
    [
        b"not json",
        b"{}",
        b'{"choices": []}',
        completion(None),
        completion(["a"]),
        completion("   "),
        completion("<think>only thinking</think>"),
    ],
)
def test_unusable_replies_are_unavailable(make_stub: Any, body: bytes) -> None:
    stub = make_stub((200, {}, body))
    with pytest.raises(LanguageModelUnavailableError):
        model_for(stub).generate(MESSAGES)


def test_an_oversized_reply_is_refused(make_stub: Any) -> None:
    stub = make_stub((200, {}, completion("x" * (1024 * 1024 + 10))))
    with pytest.raises(LanguageModelUnavailableError):
        model_for(stub).generate(MESSAGES)


def test_a_server_that_is_not_there_is_unavailable() -> None:
    settings = make_settings(
        llm_provider="openai_compatible",
        llm_base_url="http://127.0.0.1:9/v1",
        llm_model="synthetic-model",
        llm_max_retries=1,
        llm_timeout_seconds=2,
    )
    sleeps: list[float] = []
    model = OpenAICompatibleChatModel(settings, sleep=sleeps.append, random_fraction=lambda: 0.0)

    with pytest.raises(LanguageModelUnavailableError):
        model.generate(MESSAGES)
    assert len(sleeps) == 1


def test_the_key_the_question_and_the_reply_are_never_logged(
    make_stub: Any, caplog: pytest.LogCaptureFixture
) -> None:
    caplog.set_level(logging.DEBUG)
    reply = "Synthetic confidential reply text."
    for script in ((200, {}, completion(reply)), (500, {}, completion(reply)), (200, {}, b"x")):
        model = model_for(make_stub(script))
        try:
            model.generate(MESSAGES)
        except LanguageModelUnavailableError:
            pass

    logged = caplog.text
    assert KEY not in logged
    assert QUESTION not in logged
    assert reply not in logged


def test_hosted_means_a_host_that_is_not_this_computer(make_stub: Any) -> None:
    local = model_for(make_stub())
    assert (local.provider, local.hosted) == ("openai_compatible", False)
    assert provider_of(local) == "openai_compatible"
    assert sends_text_off_device(local) is False

    settings = make_settings(
        llm_provider="openai_compatible",
        llm_base_url="https://api.example.test/v1",
        llm_model="synthetic-model",
        llm_api_key=KEY,
    )
    hosted = OpenAICompatibleChatModel(settings)
    assert sends_text_off_device(hosted) is True


def test_stand_ins_have_the_provider_other_and_stay_on_the_device() -> None:
    class Plain:
        name = "x"

    assert provider_of(Plain()) == "other"  # type: ignore[arg-type]
    assert sends_text_off_device(Plain()) is False  # type: ignore[arg-type]
    assert provider_of(OllamaChatModel(make_settings(llm_provider="ollama"))) == "ollama"


def test_the_settings_for_a_provider_are_checked() -> None:
    base: dict[str, Any] = {"llm_provider": "openai_compatible"}
    with pytest.raises(ValidationError):
        make_settings(**base)
    with pytest.raises(ValidationError):
        make_settings(**base, llm_base_url="https://api.example.test/v1")
    with pytest.raises(ValidationError):
        make_settings(**base, llm_base_url="ftp://api.example.test", llm_model="m")
    with pytest.raises(ValidationError):
        make_settings(**base, llm_base_url="https://user:pw@api.example.test", llm_model="m")
    # A host that isn't this computer needs https and a key.
    with pytest.raises(ValidationError):
        make_settings(
            **base, llm_base_url="http://api.example.test/v1", llm_model="m", llm_api_key=KEY
        )
    with pytest.raises(ValidationError):
        make_settings(**base, llm_base_url="https://api.example.test/v1", llm_model="m")
    with pytest.raises(ValidationError):
        make_settings(llm_token_limit_parameter="other")

    local = make_settings(**base, llm_base_url="http://localhost:11434/v1/", llm_model="m")
    assert local.llm_base_url == "http://localhost:11434/v1"
    assert local.llm_is_hosted is False
    hosted = make_settings(
        **base, llm_base_url="https://api.example.test/v1", llm_model="m", llm_api_key=KEY
    )
    assert hosted.llm_is_hosted is True
    assert KEY not in repr(hosted)
