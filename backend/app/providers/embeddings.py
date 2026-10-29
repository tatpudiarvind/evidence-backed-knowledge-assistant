"""Embedding providers: turn text into vectors for semantic search (Phase 3, D-34)."""

import logging
import math
import os
import threading
from collections.abc import Sequence
from pathlib import Path
from typing import TYPE_CHECKING, Protocol

from app.core.config import Settings
from app.domain.indexing import EMBEDDING_DIMENSION

if TYPE_CHECKING:
    from sentence_transformers import SentenceTransformer

logger = logging.getLogger(__name__)


def configure_hugging_face(model_dir: Path, *, offline: bool) -> None:
    """Keep Hugging Face's files in the model folder and turn off its telemetry.

    Offline, as when the server loads the model, its progress bars are turned off too. Its
    libraries read these settings once, when first imported, so call this before that. Values
    already set in the environment win.
    """
    os.environ.setdefault("HF_HOME", str(model_dir / ".hf-home"))
    os.environ.setdefault("HF_HUB_DISABLE_TELEMETRY", "1")
    # Plain HTTPS downloads, without the optional Xet storage client.
    os.environ.setdefault("HF_HUB_DISABLE_XET", "1")
    # Without symbolic-link rights on Windows, the cache copies files instead, which is fine.
    os.environ.setdefault("HF_HUB_DISABLE_SYMLINKS_WARNING", "1")
    if offline:
        os.environ.setdefault("HF_HUB_OFFLINE", "1")
        # Loading the model would otherwise draw a progress bar in the server's log.
        os.environ.setdefault("HF_HUB_DISABLE_PROGRESS_BARS", "1")


class EmbeddingUnavailableError(Exception):
    """The model can't be loaded, for example because it hasn't been downloaded yet."""


class EmbeddingProvider(Protocol):
    def embed_documents(self, texts: Sequence[str]) -> list[list[float]]: ...

    def embed_query(self, text: str) -> list[float]: ...


class SentenceTransformerEmbeddings:
    """A sentence-transformers model run on the CPU, from files already downloaded.

    The model loads on first use, so the API starts quickly and still serves everything else
    when the model is missing. A failed load is tried again next time, so downloading the
    model needs no restart. Work runs one batch at a time, because the tokenizer can't be used
    from two threads at once.
    """

    def __init__(self, settings: Settings) -> None:
        self._name = settings.embedding_model_name
        self._revision = settings.embedding_model_revision
        self._model_dir = settings.embedding_model_dir
        self._batch_size = settings.embedding_batch_size
        self._query_prefix = settings.embedding_query_prefix
        self._model: SentenceTransformer | None = None
        self._lock = threading.Lock()

    def embed_documents(self, texts: Sequence[str]) -> list[list[float]]:
        vectors: list[list[float]] = []
        for start in range(0, len(texts), self._batch_size):
            batch = list(texts[start : start + self._batch_size])
            with self._lock:
                encoded = self._loaded_model().encode_document(
                    batch,
                    batch_size=self._batch_size,
                    normalize_embeddings=True,
                    show_progress_bar=False,
                )
            vectors.extend(encoded.tolist())
        return vectors

    def embed_query(self, text: str) -> list[float]:
        with self._lock:
            encoded = self._loaded_model().encode_query(
                [text],
                prompt=self._query_prefix,
                normalize_embeddings=True,
                show_progress_bar=False,
            )
        vector: list[float] = encoded[0].tolist()
        return vector

    def _loaded_model(self) -> "SentenceTransformer":
        if self._model is None:
            self._model = self._load()
        return self._model

    def _load(self) -> "SentenceTransformer":
        # Indexing never downloads: `python -m app.cli download-embedding-model` does that.
        configure_hugging_face(self._model_dir, offline=True)
        try:
            from sentence_transformers import SentenceTransformer

            model = SentenceTransformer(
                self._name,
                device="cpu",
                cache_folder=str(self._model_dir),
                revision=self._revision,
                local_files_only=True,
                trust_remote_code=False,
            )
            dimension = model.get_embedding_dimension()
        except Exception as error:
            logger.warning(
                "Embedding model %s is unavailable (%s). Download it with "
                "`python -m app.cli download-embedding-model`.",
                self._name,
                type(error).__name__,
            )
            raise EmbeddingUnavailableError(self._name) from error
        if dimension != EMBEDDING_DIMENSION:
            logger.warning(
                "Embedding model %s makes %s-dimensional vectors; the database stores %s",
                self._name,
                dimension,
                EMBEDDING_DIMENSION,
            )
            raise EmbeddingUnavailableError(self._name)
        logger.info("Loaded embedding model %s", self._name)
        return model


def check_vectors(vectors: Sequence[Sequence[float]], expected_count: int) -> bool:
    """Whether a provider returned one finite vector of the right size for each text."""
    return len(vectors) == expected_count and all(
        len(vector) == EMBEDDING_DIMENSION and all(math.isfinite(value) for value in vector)
        for vector in vectors
    )
