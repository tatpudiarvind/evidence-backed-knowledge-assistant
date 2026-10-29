"""Language models that write answers from the passages found for a question (Phase 4)."""

import http.client
import json
import logging
import time
import urllib.error
import urllib.request
from collections.abc import Sequence
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


class LanguageModelUnavailableError(Exception):
    """The model gave no usable reply: its server isn't running, the model isn't installed,
    it ran out of time, or its reply was empty."""


class LanguageModel(Protocol):
    @property
    def name(self) -> str: ...

    def generate(self, messages: Sequence[ChatMessage]) -> Generation: ...


class OllamaChatModel:
    """A model served by an Ollama server, through its chat API.

    Requests go straight to the configured address, never through a proxy set in the
    environment, and offer the model no tools: all it can do is return text.
    """

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
