"""Language models that write answers from the passages found for a question (Phase 4)."""

import http.client
import json
import logging
import random
import time
import urllib.error
import urllib.request
from collections.abc import Callable, Sequence
from dataclasses import dataclass
from typing import Any, Protocol

from app.core.config import MAX_ANSWER_TOKENS, Settings
from app.domain.grounding import ChatMessage

logger = logging.getLogger(__name__)

# A reply is a few thousand characters; a response far larger than that isn't one.
_MAX_RESPONSE_BYTES = 1024 * 1024
# Describing the model is a quick lookup, never worth a long wait.
_DESCRIBE_TIMEOUT_SECONDS = 10


@dataclass(frozen=True)
class Generation:
    text: str
    model_name: str
    # Token counts, when the provider reports them.
    prompt_tokens: int | None = None
    completion_tokens: int | None = None


class LanguageModelUnavailableError(Exception):
    """The model gave no usable reply: its server isn't running, the model isn't installed,
    it ran out of time, or its reply was empty."""


class LanguageModel(Protocol):
    @property
    def name(self) -> str: ...

    def generate(self, messages: Sequence[ChatMessage]) -> Generation: ...


def provider_of(model: LanguageModel) -> str:
    """The provider a model belongs to, as recorded with its answers: `ollama`,
    `openai_compatible`, or `other` for any stand-in."""
    provider = getattr(model, "provider", None)
    return provider if isinstance(provider, str) else "other"


def sends_text_off_device(model: LanguageModel) -> bool:
    """Whether the passages and question leave this computer to reach the model."""
    return getattr(model, "hosted", False) is True


# The longest wait between two tries, whatever a server asks for.
_MAX_RETRY_WAIT_SECONDS = 30.0
_RETRY_STATUSES = frozenset({429, 500, 502, 503, 504})


class _NoRedirects(urllib.request.HTTPRedirectHandler):
    """Refuses redirects, which would carry the key to whatever host they name."""

    def redirect_request(self, *args: Any, **kwargs: Any) -> None:
        return None


class OpenAICompatibleChatModel:
    """A model behind any server that speaks the OpenAI chat completions API (Phase 9): a hosted
    provider, or a local server such as Ollama's `/v1` endpoint.

    The reply is only ever text: no tools or functions are offered. The key goes only in the
    Authorization header; it, the request, and the reply are never logged. A server on this
    computer is reached without any proxy set in the environment; a hosted one is reached the
    way the environment's proxy settings say.
    """

    provider = "openai_compatible"

    def __init__(
        self,
        settings: Settings,
        *,
        sleep: Callable[[float], None] = time.sleep,
        random_fraction: Callable[[], float] = random.random,
    ) -> None:
        assert settings.llm_base_url and settings.llm_model
        self._url = f"{settings.llm_base_url}/chat/completions"
        self._model = settings.llm_model
        self._key = settings.llm_api_key.get_secret_value() if settings.llm_api_key else None
        self._timeout = settings.llm_timeout_seconds
        self._token_parameter = settings.llm_token_limit_parameter
        self._max_retries = settings.llm_max_retries
        self.hosted = settings.llm_is_hosted
        self._sleep = sleep
        self._random = random_fraction
        self._opener = urllib.request.build_opener(
            _NoRedirects,
            *([] if self.hosted else [urllib.request.ProxyHandler({})]),
        )

    @property
    def name(self) -> str:
        return self._model

    def generate(self, messages: Sequence[ChatMessage]) -> Generation:
        body = {
            "model": self._model,
            "messages": [
                {"role": message.role, "content": message.content} for message in messages
            ],
            "temperature": 0,
            self._token_parameter: MAX_ANSWER_TOKENS,
            "stream": False,
        }
        headers = {"Content-Type": "application/json"}
        if self._key:
            headers["Authorization"] = f"Bearer {self._key}"
        payload = json.dumps(body).encode("utf-8")
        started = time.perf_counter()
        raw = self._post(payload, headers)
        try:
            reply = json.loads(raw)
            content = reply["choices"][0]["message"]["content"]
            if not isinstance(content, str):
                raise TypeError("The reply isn't text")
        except (ValueError, KeyError, IndexError, TypeError) as error:
            logger.warning(
                "Model %s gave a reply that isn't usable (%s)", self._model, type(error).__name__
            )
            raise LanguageModelUnavailableError(self._model) from error
        text = strip_thinking(content)
        if not text:
            logger.warning("Model %s gave an empty reply", self._model)
            raise LanguageModelUnavailableError(self._model)
        usage = reply.get("usage") if isinstance(reply, dict) else None
        logger.info("Model %s replied in %.1f s", self._model, time.perf_counter() - started)
        return Generation(
            text, self._model, _count(usage, "prompt_tokens"), _count(usage, "completion_tokens")
        )

    def _post(self, payload: bytes, headers: dict[str, str]) -> bytes:
        """The reply's bytes, after retrying a busy or failing server."""
        for attempt in range(self._max_retries + 1):
            request = urllib.request.Request(
                self._url, data=payload, headers=headers, method="POST"
            )
            wait: float | None = None
            try:
                with self._opener.open(request, timeout=self._timeout) as response:
                    raw: bytes = response.read(_MAX_RESPONSE_BYTES + 1)
                if len(raw) > _MAX_RESPONSE_BYTES:
                    logger.warning("Model %s gave a reply that is too large", self._model)
                    raise LanguageModelUnavailableError(self._model)
                return raw
            except urllib.error.HTTPError as error:
                retry_after = error.headers.get("Retry-After") if error.headers else None
                error.close()
                # Only the status is logged: a reply's body could hold the question's text.
                logger.warning("Model %s: the server answered HTTP %s", self._model, error.code)
                if error.code not in _RETRY_STATUSES:
                    raise LanguageModelUnavailableError(self._model) from error
                wait = self._wait(attempt, retry_after)
            except (OSError, http.client.HTTPException) as error:
                logger.warning("Model %s is unreachable (%s)", self._model, type(error).__name__)
                wait = self._wait(attempt, None)
            if attempt == self._max_retries:
                break
            self._sleep(wait)
        raise LanguageModelUnavailableError(self._model)

    def _wait(self, attempt: int, retry_after: str | None) -> float:
        if retry_after:
            try:
                return min(max(float(retry_after), 0.0), _MAX_RETRY_WAIT_SECONDS)
            except ValueError:
                pass
        # Exponential, from one second, with up to a quarter added so clients don't move together.
        return min(2.0**attempt * (1 + 0.25 * self._random()), _MAX_RETRY_WAIT_SECONDS)


def _count(usage: Any, key: str) -> int | None:
    value = usage.get(key) if isinstance(usage, dict) else None
    return value if isinstance(value, int) and not isinstance(value, bool) and value >= 0 else None


class OllamaChatModel:
    """A model served by an Ollama server, through its chat API.

    Requests go straight to the configured address, never through a proxy set in the
    environment, and offer the model no tools: all it can do is return text.
    """

    provider = "ollama"
    hosted = False

    def __init__(self, settings: Settings) -> None:
        self._base_url = settings.ollama_base_url
        self._url = f"{self._base_url}/api/chat"
        self._model = settings.ollama_model
        self._timeout = settings.llm_timeout_seconds
        self._context_tokens = settings.ollama_context_tokens
        self._opener = urllib.request.build_opener(urllib.request.ProxyHandler({}))

    @property
    def name(self) -> str:
        return self._model

    def describe(self) -> dict[str, str | None]:
        """The server's version, and the model's digest, size, and quantization, as the server
        reports them, to record which model produced a set of answers. None for anything the
        server doesn't report, or if it doesn't respond."""
        version = self._get_json("/api/version")
        tags = self._get_json("/api/tags")
        listed = tags.get("models") if isinstance(tags, dict) else None
        # Ollama lists a model pulled without a tag under the tag "latest".
        names = {self._model, self._model if ":" in self._model else f"{self._model}:latest"}
        entry = next(
            (
                model
                for model in (listed if isinstance(listed, list) else [])
                if isinstance(model, dict) and model.get("name") in names
            ),
            {},
        )
        details = entry.get("details")
        return {
            "name": self._model,
            "server_version": _text(version, "version"),
            "digest": _text(entry, "digest"),
            "parameter_size": _text(details, "parameter_size"),
            "quantization_level": _text(details, "quantization_level"),
        }

    def generate(self, messages: Sequence[ChatMessage]) -> Generation:
        body = {
            "model": self._model,
            "messages": [
                {"role": message.role, "content": message.content} for message in messages
            ],
            "stream": False,
            "options": {
                # The same passages and question give the same answer.
                "temperature": 0,
                "num_ctx": self._context_tokens,
                "num_predict": MAX_ANSWER_TOKENS,
            },
        }
        request = urllib.request.Request(
            self._url,
            data=json.dumps(body).encode("utf-8"),
            headers={"Content-Type": "application/json"},
            method="POST",
        )
        started = time.perf_counter()
        try:
            with self._opener.open(request, timeout=self._timeout) as response:
                raw = response.read(_MAX_RESPONSE_BYTES + 1)
            if len(raw) > _MAX_RESPONSE_BYTES:
                raise ValueError("The response is too large")
            content = json.loads(raw)["message"]["content"]
            if not isinstance(content, str):
                raise TypeError("The reply isn't text")
        except urllib.error.HTTPError as error:
            error.close()
            # 404 means the model hasn't been pulled.
            logger.warning(
                "Model %s is unavailable: Ollama answered HTTP %s", self._model, error.code
            )
            raise LanguageModelUnavailableError(self._model) from error
        except (OSError, http.client.HTTPException, ValueError, KeyError, TypeError) as error:
            # Includes refused connections, timeouts, and replies that aren't Ollama's JSON.
            logger.warning("Model %s is unavailable (%s)", self._model, type(error).__name__)
            raise LanguageModelUnavailableError(self._model) from error
        text = strip_thinking(content)
        if not text:
            logger.warning("Model %s gave an empty reply", self._model)
            raise LanguageModelUnavailableError(self._model)
        logger.info("Model %s replied in %.1f s", self._model, time.perf_counter() - started)
        return Generation(text, self._model)

    def _get_json(self, path: str) -> Any:
        """The JSON the server returns for a GET request, or None if it returns none."""
        request = urllib.request.Request(f"{self._base_url}{path}", method="GET")
        timeout = min(self._timeout, _DESCRIBE_TIMEOUT_SECONDS)
        try:
            with self._opener.open(request, timeout=timeout) as response:
                raw = response.read(_MAX_RESPONSE_BYTES + 1)
            if len(raw) > _MAX_RESPONSE_BYTES:
                return None
            return json.loads(raw)
        except urllib.error.HTTPError as error:
            error.close()
            return None
        except (OSError, http.client.HTTPException, ValueError):
            return None


def _text(value: Any, key: str) -> str | None:
    found = value.get(key) if isinstance(value, dict) else None
    return found if isinstance(found, str) else None


def strip_thinking(content: str) -> str:
    """A reply without the reasoning that some models write before it, between think tags."""
    if "</think>" in content:
        return content.rsplit("</think>", 1)[1].strip()
    if "<think>" in content:
        # The model ran out of room while still reasoning, so it never replied.
        return ""
    return content.strip()
