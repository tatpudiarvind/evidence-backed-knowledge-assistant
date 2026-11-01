"""The reranker (P7-05; D-81), mostly with a stand-in for the sentence-transformers cross-encoder.

One test runs the real library without the model's files, to show that it takes the adapter's
options and that a question never downloads anything. The last test uses the real model when it
has been downloaded (`-m model` selects it with the embedding model's test). Unlike that test,
it is skipped without the model even when TEST_MODEL_REQUIRED=1: CI doesn't download the
reranker.
"""

import socket
import sys
import types
from collections.abc import Callable
from pathlib import Path
from typing import Any

import numpy as np
import pytest
from fastapi import FastAPI

from app.core.config import Settings
from app.providers import rerankers
from app.providers.rerankers import CrossEncoderReranker, RerankerUnavailableError
from tests.support import LengthReranker, make_settings

PREDICT_OPTIONS = {"show_progress_bar": False, "convert_to_numpy": True}


class FakeLibrary:
    """Stands in for the sentence-transformers package, recording how the model is used."""

    def __init__(self) -> None:
        self.configured: list[tuple[Path, bool]] = []
        self.created: list[dict[str, Any]] = []
        self.calls: list[tuple[list[tuple[str, str]], dict[str, Any]]] = []
        self.load_errors: list[Exception] = []
        self.predict_errors: list[Exception] = []

    def configure(self, model_dir: Path, *, offline: bool) -> None:
        self.configured.append((model_dir, offline))

    def module(self) -> types.ModuleType:
        library = self

        class CrossEncoder:
            def __init__(self, name: str, **options: Any) -> None:
                if library.load_errors:
                    raise library.load_errors.pop(0)
                library.created.append({"name": name, **options})

            def predict(self, pairs: list[tuple[str, str]], **options: Any) -> np.ndarray:
                library.calls.append((list(pairs), options))
                if library.predict_errors:
                    raise library.predict_errors.pop(0)
                # Longer passages score higher, in the real model's number type.
                return np.array([len(text) for _, text in pairs], dtype=np.float32)

        module = types.ModuleType("sentence_transformers")
        module.CrossEncoder = CrossEncoder  # type: ignore[attr-defined]
        return module


@pytest.fixture
def library(monkeypatch: pytest.MonkeyPatch) -> FakeLibrary:
    fake = FakeLibrary()
    monkeypatch.setitem(sys.modules, "sentence_transformers", fake.module())
    monkeypatch.setattr(rerankers, "configure_hugging_face", fake.configure)
    return fake


def test_the_model_loads_once_on_first_use_from_local_files(
    library: FakeLibrary, tmp_path: Path
) -> None:
    settings = make_settings(embedding_model_dir=tmp_path)
    reranker = CrossEncoderReranker(settings)
    assert reranker.name == "cross-encoder/ms-marco-MiniLM-L6-v2"
    assert library.created == []

    reranker.score("When?", ["one"])
    reranker.score("Why?", ["two"])

    assert library.configured == [(tmp_path, True)]
    assert library.created == [
        {
            "name": settings.reranker_model_name,
            "device": "cpu",
            "cache_folder": str(tmp_path),
            "revision": settings.reranker_model_revision,
            "local_files_only": True,
            "trust_remote_code": False,
        }
    ]


def test_each_passage_is_scored_with_the_question(library: FakeLibrary, tmp_path: Path) -> None:
    reranker = CrossEncoderReranker(
        make_settings(embedding_model_dir=tmp_path, embedding_batch_size=8)
    )

    scores = reranker.score("When?", ["short", "a longer text"])

    assert scores == [5.0, 13.0]
    assert all(type(score) is float for score in scores)
    assert library.calls == [
        ([("When?", "short"), ("When?", "a longer text")], {"batch_size": 8, **PREDICT_OPTIONS})
    ]


def test_no_passages_need_no_model(library: FakeLibrary, tmp_path: Path) -> None:
    reranker = CrossEncoderReranker(make_settings(embedding_model_dir=tmp_path))

    assert reranker.score("When?", []) == []
    assert (library.configured, library.created, library.calls) == ([], [], [])


def test_a_failed_load_is_tried_again_next_time(
    library: FakeLibrary, tmp_path: Path, caplog: pytest.LogCaptureFixture
) -> None:
    library.load_errors.append(OSError("synthetic secret path"))
    reranker = CrossEncoderReranker(make_settings(embedding_model_dir=tmp_path))

    with pytest.raises(RerankerUnavailableError):
        reranker.score("When?", ["one"])

    assert "download-reranker-model" in caplog.text
    assert "OSError" in caplog.text
    assert "synthetic secret path" not in caplog.text
    assert reranker.score("When?", ["one"]) == [3.0]
    assert len(library.created) == 1


def test_a_failed_scoring_reports_only_the_error_type(
    library: FakeLibrary, tmp_path: Path, caplog: pytest.LogCaptureFixture
) -> None:
    library.predict_errors.append(RuntimeError("synthetic secret text"))
    reranker = CrossEncoderReranker(make_settings(embedding_model_dir=tmp_path))

    with pytest.raises(RerankerUnavailableError):
        reranker.score("A private question?", ["A private passage."])

    assert "RuntimeError" in caplog.text
    for secret in ("synthetic secret text", "A private question?", "A private passage."):
        assert secret not in caplog.text
    # The model stays loaded, and the next question is scored.
    assert reranker.score("When?", ["two"]) == [3.0]
    assert len(library.created) == 1


@pytest.mark.parametrize(
    ("mode", "reranker_type"),
    [("vector", type(None)), ("hybrid", type(None)), ("hybrid_rerank", CrossEncoderReranker)],
)
def test_only_hybrid_rerank_mode_gives_the_app_the_reranker(
    make_app: Callable[..., FastAPI], mode: str, reranker_type: type[object]
) -> None:
    assert type(make_app(retrieval_mode=mode).state.reranker) is reranker_type


def test_an_app_given_a_reranker_uses_it(make_app: Callable[..., FastAPI]) -> None:
    stand_in = LengthReranker()

    assert make_app(retrieval_mode="hybrid_rerank", reranker=stand_in).state.reranker is stand_in


@pytest.mark.usefixtures("clean_hf_environment")
def test_without_its_files_the_real_model_is_unavailable_and_nothing_is_downloaded(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path, caplog: pytest.LogCaptureFixture
) -> None:
    connections: list[object] = []

    def refuse(self: socket.socket, address: object) -> None:
        connections.append(address)
        raise ConnectionRefusedError("This test doesn't use the network")

    monkeypatch.setattr(socket.socket, "connect", refuse)
    reranker = CrossEncoderReranker(make_settings(embedding_model_dir=tmp_path))

    with pytest.raises(RerankerUnavailableError) as raised:
        reranker.score("How long are records kept?", ["Records are kept for seven years."])

    # The library took every option and only missed the files.
    assert type(raised.value.__cause__) is OSError
    assert connections == []
    assert "download-reranker-model" in caplog.text


@pytest.mark.model
@pytest.mark.usefixtures("clean_hf_environment")
def test_the_real_reranker_prefers_the_passage_that_answers() -> None:
    settings = Settings()
    snapshot = (
        settings.embedding_model_dir
        / f"models--{settings.reranker_model_name.replace('/', '--')}"
        / "snapshots"
        / settings.reranker_model_revision
    )
    if not snapshot.is_dir():
        pytest.skip("Reranker not downloaded: run `python -m app.cli download-reranker-model`")
    reranker = CrossEncoderReranker(settings)

    answer, unrelated = reranker.score(
        "How long are records kept?",
        [
            "Synthetic policy: project records are kept for seven years, then deleted.",
            "The office cafeteria serves soup and sandwiches from noon.",
        ],
    )

    assert answer > unrelated
