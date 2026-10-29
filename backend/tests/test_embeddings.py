"""The embedding provider (P3-05), mostly with a stand-in for the sentence-transformers model.

The last test uses the real model when it has been downloaded (`-m model` selects it alone).
Without the model it is skipped, or fails when TEST_MODEL_REQUIRED=1, as in CI.
"""

import math
import os
import sys
import types
from pathlib import Path
from typing import Any

import numpy as np
import pytest

from app.core.config import Settings
from app.domain.indexing import EMBEDDING_DIMENSION
from app.providers import embeddings
from app.providers.embeddings import (
    EmbeddingUnavailableError,
    SentenceTransformerEmbeddings,
    check_vectors,
    configure_hugging_face,
)
from tests.support import hashed_vector, make_settings

HF_VARIABLES = (
    "HF_HOME",
    "HF_HUB_DISABLE_TELEMETRY",
    "HF_HUB_DISABLE_XET",
    "HF_HUB_DISABLE_SYMLINKS_WARNING",
    "HF_HUB_OFFLINE",
    "HF_HUB_DISABLE_PROGRESS_BARS",
)
ENCODE_OPTIONS = {"normalize_embeddings": True, "show_progress_bar": False}


class FakeLibrary:
    """Stands in for the sentence-transformers package, recording how the model is used."""

    def __init__(self) -> None:
        self.configured: list[tuple[Path, bool]] = []
        self.created: list[dict[str, Any]] = []
        self.calls: list[tuple[str, list[str], dict[str, Any]]] = []
        self.load_errors: list[Exception] = []
        self.dimension = EMBEDDING_DIMENSION

    def configure(self, model_dir: Path, *, offline: bool) -> None:
        self.configured.append((model_dir, offline))

    def module(self) -> types.ModuleType:
        library = self

        class SentenceTransformer:
            def __init__(self, name: str, **options: Any) -> None:
                if library.load_errors:
                    raise library.load_errors.pop(0)
                library.created.append({"name": name, **options})

            def get_embedding_dimension(self) -> int:
                return library.dimension

            def encode_document(self, texts: list[str], **options: Any) -> np.ndarray:
                library.calls.append(("document", texts, options))
                return np.array([hashed_vector(text) for text in texts])

            def encode_query(self, texts: list[str], **options: Any) -> np.ndarray:
                library.calls.append(("query", texts, options))
                return np.array([hashed_vector(text) for text in texts])

        module = types.ModuleType("sentence_transformers")
        module.SentenceTransformer = SentenceTransformer  # type: ignore[attr-defined]
        return module


@pytest.fixture
def library(monkeypatch: pytest.MonkeyPatch) -> FakeLibrary:
    fake = FakeLibrary()
    monkeypatch.setitem(sys.modules, "sentence_transformers", fake.module())
    monkeypatch.setattr(embeddings, "configure_hugging_face", fake.configure)
    return fake


@pytest.fixture
def clean_hf_environment(monkeypatch: pytest.MonkeyPatch) -> None:
    """Remove Hugging Face settings for one test, and put back afterwards whatever was there."""
    for name in HF_VARIABLES:
        # Setting first makes monkeypatch restore the variable, even if it didn't exist.
        monkeypatch.setenv(name, "")
        monkeypatch.delenv(name)


def _settings(model_dir: Path, **overrides: Any) -> Settings:
    return make_settings(embedding_model_dir=model_dir, **overrides)


def test_the_model_loads_once_on_first_use_from_local_files(
    library: FakeLibrary, tmp_path: Path
) -> None:
    settings = _settings(tmp_path)
    provider = SentenceTransformerEmbeddings(settings)
    assert library.created == []

    provider.embed_documents(["one"])
    provider.embed_query("two")

    assert library.configured == [(tmp_path, True)]
    assert library.created == [
        {
            "name": settings.embedding_model_name,
            "device": "cpu",
            "cache_folder": str(tmp_path),
            "revision": settings.embedding_model_revision,
            "local_files_only": True,
            "trust_remote_code": False,
        }
    ]


def test_documents_are_embedded_in_batches(library: FakeLibrary, tmp_path: Path) -> None:
    texts = ["a", "b", "c", "d", "e"]
    provider = SentenceTransformerEmbeddings(_settings(tmp_path, embedding_batch_size=2))

    vectors = provider.embed_documents(texts)

    assert vectors == [hashed_vector(text) for text in texts]
    options = {"batch_size": 2, **ENCODE_OPTIONS}
    assert library.calls == [
        ("document", ["a", "b"], options),
        ("document", ["c", "d"], options),
        ("document", ["e"], options),
    ]


def test_queries_get_the_model_prefix(library: FakeLibrary, tmp_path: Path) -> None:
    settings = _settings(tmp_path)
    question = "When are records deleted?"

    vector = SentenceTransformerEmbeddings(settings).embed_query(question)

    assert vector == hashed_vector(question)
    options = {"prompt": settings.embedding_query_prefix, **ENCODE_OPTIONS}
    assert library.calls == [("query", [question], options)]


def test_a_failed_load_is_tried_again_next_time(
    library: FakeLibrary, tmp_path: Path, caplog: pytest.LogCaptureFixture
) -> None:
    library.load_errors.append(OSError("synthetic secret path"))
    provider = SentenceTransformerEmbeddings(_settings(tmp_path))

    with pytest.raises(EmbeddingUnavailableError):
        provider.embed_documents(["one"])

    assert "download-embedding-model" in caplog.text
    assert "OSError" in caplog.text
    assert "synthetic secret path" not in caplog.text
    assert provider.embed_documents(["one"]) == [hashed_vector("one")]
    assert len(library.created) == 1


def test_models_making_vectors_of_another_size_are_refused(
    library: FakeLibrary, tmp_path: Path, caplog: pytest.LogCaptureFixture
) -> None:
    library.dimension = 768
    provider = SentenceTransformerEmbeddings(_settings(tmp_path))

    with pytest.raises(EmbeddingUnavailableError):
        provider.embed_query("question")

    assert "768-dimensional" in caplog.text
    assert library.calls == []


_VECTOR = [0.5] * EMBEDDING_DIMENSION


@pytest.mark.parametrize(
    ("vectors", "expected_count", "valid"),
    [
        ([_VECTOR, _VECTOR], 2, True),
        ([], 0, True),
        ([_VECTOR], 2, False),
        ([_VECTOR, _VECTOR[:-1]], 2, False),
        ([[*_VECTOR[:-1], math.nan]], 1, False),
        ([[*_VECTOR[:-1], math.inf]], 1, False),
    ],
    ids=["valid", "none", "too-few", "too-short", "not-a-number", "infinite"],
)
def test_check_vectors(vectors: list[list[float]], expected_count: int, valid: bool) -> None:
    assert check_vectors(vectors, expected_count) is valid


@pytest.mark.usefixtures("clean_hf_environment")
def test_hugging_face_files_stay_in_the_model_folder(tmp_path: Path) -> None:
    configure_hugging_face(tmp_path, offline=False)

    assert os.environ["HF_HOME"] == str(tmp_path / ".hf-home")
    assert os.environ["HF_HUB_DISABLE_TELEMETRY"] == "1"
    assert os.environ["HF_HUB_DISABLE_XET"] == "1"
    assert os.environ["HF_HUB_DISABLE_SYMLINKS_WARNING"] == "1"
    assert "HF_HUB_OFFLINE" not in os.environ
    assert "HF_HUB_DISABLE_PROGRESS_BARS" not in os.environ

    configure_hugging_face(tmp_path, offline=True)

    assert os.environ["HF_HUB_OFFLINE"] == "1"
    assert os.environ["HF_HUB_DISABLE_PROGRESS_BARS"] == "1"


@pytest.mark.usefixtures("clean_hf_environment")
def test_hugging_face_settings_already_made_win(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    monkeypatch.setenv("HF_HOME", str(tmp_path / "elsewhere"))
    monkeypatch.setenv("HF_HUB_OFFLINE", "0")

    configure_hugging_face(tmp_path, offline=True)

    assert os.environ["HF_HOME"] == str(tmp_path / "elsewhere")
    assert os.environ["HF_HUB_OFFLINE"] == "0"


@pytest.mark.model
@pytest.mark.usefixtures("clean_hf_environment")
def test_the_real_model_puts_related_text_closer() -> None:
    settings = Settings()
    snapshot = (
        settings.embedding_model_dir
        / f"models--{settings.embedding_model_name.replace('/', '--')}"
        / "snapshots"
        / settings.embedding_model_revision
    )
    if not snapshot.is_dir():
        message = "Model not downloaded: run `python -m app.cli download-embedding-model`"
        if os.environ.get("TEST_MODEL_REQUIRED") == "1":
            pytest.fail(message)
        pytest.skip(message)
    provider = SentenceTransformerEmbeddings(settings)

    related, unrelated = provider.embed_documents(
        [
            "Synthetic policy: project records are kept for seven years, then deleted.",
            "The office cafeteria serves soup and sandwiches from noon.",
        ]
    )
    question = provider.embed_query("How long are records kept?")

    for vector in (related, unrelated, question):
        assert len(vector) == EMBEDDING_DIMENSION
        assert math.isclose(math.hypot(*vector), 1.0, abs_tol=1e-3)
    assert np.dot(question, related) > np.dot(question, unrelated)
