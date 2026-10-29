"""Language models that write answers from the passages found for a question (Phase 4)."""

import http.client
import json
import logging
import time
import urllib.error
import urllib.request
from collections.abc import Sequence
from dataclasses import dataclass
from typing import Protocol

from app.core.config import MAX_ANSWER_TOKENS, Settings
from app.domain.grounding import ChatMessage

logger = logging.getLogger(__name__)

# A reply is a few thousand characters; a response far larger than that isn't one.
_MAX_RESPONSE_BYTES = 1024 * 1024


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
        self._url = f"{settings.ollama_base_url}/api/chat"
        self._model = settings.ollama_model
        self._timeout = settings.llm_timeout_seconds
        self._context_tokens = settings.ollama_context_tokens
        self._opener = urllib.request.build_opener(urllib.request.ProxyHandler({}))

    @property
    def name(self) -> str:
        return self._model

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


def strip_thinking(content: str) -> str:
    """A reply without the reasoning that some models write before it, between think tags."""
    if "</think>" in content:
        return content.rsplit("</think>", 1)[1].strip()
    if "<think>" in content:
        # The model ran out of room while still reasoning, so it never replied.
        return ""
    return content.strip()
