"""Rerankers (Phase 7, D-81): score how well passages match a question, to reorder them.

A cross-encoder reads the question and a passage together. That judges their match better than
comparing two embeddings, but takes longer, so it only scores the candidates that hybrid search
already found.
"""

import logging
import threading
from collections.abc import Sequence
from typing import TYPE_CHECKING, Protocol

from app.core.config import Settings
from app.providers.embeddings import configure_hugging_face

if TYPE_CHECKING:
    from sentence_transformers import CrossEncoder

logger = logging.getLogger(__name__)


class RerankerUnavailableError(Exception):
    """The reranker can't be loaded or run, for example because it hasn't been downloaded."""


class Reranker(Protocol):
    @property
    def name(self) -> str: ...

    def score(self, question: str, texts: Sequence[str]) -> list[float]:
        """One score for each text, higher for a better match. Only their order matters."""
        ...


class CrossEncoderReranker:
    """A sentence-transformers cross-encoder run on the CPU, from files already downloaded.

    Like the embedding model, it loads on first use, and a failed load is tried again next
    time, so downloading the model needs no restart. It scores one question at a time, because
    the tokenizer can't be used from two threads at once.
    """

    def __init__(self, settings: Settings) -> None:
        self._name = settings.reranker_model_name
        self._revision = settings.reranker_model_revision
        self._model_dir = settings.embedding_model_dir
        self._batch_size = settings.embedding_batch_size
        self._model: CrossEncoder | None = None
        self._lock = threading.Lock()

    @property
    def name(self) -> str:
        return self._name

    def score(self, question: str, texts: Sequence[str]) -> list[float]:
        if not texts:
            return []
        pairs = [(question, text) for text in texts]
        with self._lock:
            model = self._loaded_model()
            try:
                scores = model.predict(
                    pairs,
                    batch_size=self._batch_size,
                    show_progress_bar=False,
                    convert_to_numpy=True,
                )
                values: list[float] = [float(value) for value in scores.tolist()]
            except Exception as error:
                logger.warning("Reranker %s failed (%s)", self._name, type(error).__name__)
                raise RerankerUnavailableError(self._name) from error
        return values

    def _loaded_model(self) -> "CrossEncoder":
        if self._model is None:
            self._model = self._load()
        return self._model

    def _load(self) -> "CrossEncoder":
        # Questions never download: `python -m app.cli download-reranker-model` does that.
        configure_hugging_face(self._model_dir, offline=True)
        try:
            from sentence_transformers import CrossEncoder

            model = CrossEncoder(
                self._name,
                device="cpu",
                cache_folder=str(self._model_dir),
                revision=self._revision,
                local_files_only=True,
                trust_remote_code=False,
            )
        except Exception as error:
            logger.warning(
                "Reranker %s is unavailable (%s). Download it with "
                "`python -m app.cli download-reranker-model`.",
                self._name,
                type(error).__name__,
            )
            raise RerankerUnavailableError(self._name) from error
        logger.info("Loaded reranker %s", self._name)
        return model
