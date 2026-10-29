"""The maintenance command line (P3-05, P5-02), with stand-ins for the download and the
models."""

import json
import sys
import types
from collections.abc import Callable
from pathlib import Path
from typing import Any

import pytest
from sqlalchemy import make_url

from app import cli
from app.core.config import Settings
from app.domain.indexing import EMBEDDING_DIMENSION
from app.evaluation.dataset import questions_sha256
from app.providers.embeddings import EmbeddingUnavailableError
from tests.support import (
    UNREACHABLE_DATABASE_URL,
    HashingEmbeddings,
    ScriptedLanguageModel,
    make_settings,
)

QUESTION: dict[str, Any] = {
    "id": "a01",
    "category": "answerable",
    "question": "How long are project records kept?",
    "expected_sources": [{"document": "notes.txt"}],
    "expected_facts": [["seven years"]],
}


class FakeHub:
    """Stands in for huggingface_hub, truststore, and the model, recording how they're used."""

    def __init__(self, snapshot: Path) -> None:
        self.snapshot = snapshot
        self.configured: list[tuple[Path, bool]] = []
        self.trust_injected = 0
        self.downloads: list[tuple[str, dict[str, Any]]] = []
        self.download_error: Exception | None = None
        self.loaded: list[Settings] = []
        self.model_available = True

    def configure(self, model_dir: Path, *, offline: bool) -> None:
        self.configured.append((model_dir, offline))

    def inject_into_ssl(self) -> None:
        self.trust_injected += 1

    def snapshot_download(self, name: str, **options: Any) -> str:
        self.downloads.append((name, options))
        if self.download_error is not None:
            raise self.download_error
        return str(self.snapshot)

    def embeddings(self, settings: Settings) -> "FakeHub":
        self.loaded.append(settings)
        return self

    def embed_query(self, text: str) -> list[float]:
        if not self.model_available:
            raise EmbeddingUnavailableError("synthetic-model")
        return [0.0] * EMBEDDING_DIMENSION


@pytest.fixture
def hub(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> FakeHub:
    snapshot = tmp_path / "snapshot"
    (snapshot / "pooling").mkdir(parents=True)
    (snapshot / "config.json").write_text("{}")
    (snapshot / "pooling" / "config.json").write_text('{"x": 1}')
    fake = FakeHub(snapshot)
    hub_module = types.ModuleType("huggingface_hub")
    hub_module.snapshot_download = fake.snapshot_download  # type: ignore[attr-defined]
    trust_module = types.ModuleType("truststore")
    trust_module.inject_into_ssl = fake.inject_into_ssl  # type: ignore[attr-defined]
    monkeypatch.setitem(sys.modules, "huggingface_hub", hub_module)
    monkeypatch.setitem(sys.modules, "truststore", trust_module)
    monkeypatch.setattr(cli, "configure_hugging_face", fake.configure)
    monkeypatch.setattr(cli, "SentenceTransformerEmbeddings", fake.embeddings)
    return fake


def test_downloads_the_pinned_model_then_checks_it_works(
    hub: FakeHub, tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    model_dir = tmp_path / "models"
    settings = make_settings(embedding_model_dir=model_dir)

    assert cli.download_embedding_model(settings) == 0

    assert model_dir.is_dir()
    assert hub.configured == [(model_dir, False)]
    assert hub.trust_injected == 1
    assert hub.downloads == [
        (
            settings.embedding_model_name,
            {
                "revision": settings.embedding_model_revision,
                "cache_dir": model_dir,
                "allow_patterns": cli.MODEL_FILE_PATTERNS,
                "ignore_patterns": cli.SKIPPED_FILE_PATTERNS,
                "token": False,
            },
        )
    ]
    assert hub.loaded == [settings]
    output = capsys.readouterr().out
    assert "config.json (2 bytes)" in output
    assert "config.json (8 bytes)" in output
    assert "2 files, 10 bytes" in output
    assert f"makes {EMBEDDING_DIMENSION}-dimensional vectors" in output


def test_a_failed_download_is_reported(
    hub: FakeHub, tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    hub.download_error = OSError("synthetic network failure")

    assert cli.download_embedding_model(make_settings(embedding_model_dir=tmp_path)) == 1

    assert "Download failed: OSError: synthetic network failure" in capsys.readouterr().err
    assert hub.loaded == []


def test_a_model_that_does_not_load_is_reported(
    hub: FakeHub, tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    hub.model_available = False

    assert cli.download_embedding_model(make_settings(embedding_model_dir=tmp_path)) == 1

    assert "couldn't be loaded" in capsys.readouterr().err


def test_main_runs_the_command_with_the_app_settings(
    hub: FakeHub, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    settings = make_settings(embedding_model_dir=tmp_path)
    monkeypatch.setattr(cli, "get_settings", lambda: settings)

    assert cli.main(["download-embedding-model"]) == 0

    assert hub.loaded == [settings]


def test_main_needs_a_command(capsys: pytest.CaptureFixture[str]) -> None:
    with pytest.raises(SystemExit) as exited:
        cli.main([])

    assert exited.value.code == 2
    error = capsys.readouterr().err
    assert "download-embedding-model" in error
    assert "evaluate" in error


class DescribedModel(ScriptedLanguageModel):
    """A scripted model that describes itself, as the Ollama model does."""

    def describe(self) -> dict[str, str | None]:
        return {
            "name": self.name,
            "server_version": "0.0.0-synthetic",
            "digest": None,
            "parameter_size": None,
            "quantization_level": None,
        }


class UnavailableEmbeddings(HashingEmbeddings):
    def embed_query(self, text: str) -> list[float]:
        raise EmbeddingUnavailableError("synthetic-model")


def write_evaluation_data(folder: Path, *questions: dict[str, Any]) -> list[str]:
    """A corpus of one text file, and the questions. Returns the arguments that use them, and
    write the results into the folder rather than evals/results."""
    (folder / "corpus").mkdir(parents=True)
    (folder / "corpus" / "notes.txt").write_bytes(b"Project records are kept for seven years.\n")
    lines = "".join(json.dumps(question) + "\n" for question in questions)
    (folder / "questions.jsonl").write_bytes(lines.encode())
    return [
        "--corpus",
        str(folder / "corpus"),
        "--questions",
        str(folder / "questions.jsonl"),
        "--output",
        str(folder / "results.json"),
    ]


@pytest.fixture
def unit_settings(monkeypatch: pytest.MonkeyPatch) -> Settings:
    """Settings whose database nobody can reach, as the app's settings."""
    settings = make_settings()
    monkeypatch.setattr(cli, "get_settings", lambda: settings)
    return settings


def test_the_evaluation_database_is_the_apps_with_eval_added() -> None:
    url = make_url(cli.evaluation_database_url(make_settings()))

    assert url.database == "unit_tests_eval"
    assert url.set(database="unit_tests") == make_url(UNREACHABLE_DATABASE_URL)


def test_the_evaluation_only_uses_a_database_named_for_it(
    unit_settings: Settings, tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    arguments = write_evaluation_data(tmp_path, QUESTION)

    assert cli.main(["evaluate", "--database-url", UNREACHABLE_DATABASE_URL, *arguments]) == 2

    assert "has to end in _eval" in capsys.readouterr().err
    assert not (tmp_path / "results.json").exists()


def test_questions_that_do_not_match_the_corpus_are_listed(
    unit_settings: Settings, tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    arguments = write_evaluation_data(tmp_path, QUESTION | {"expected_facts": [["ten years"]]})

    assert cli.main(["evaluate", *arguments]) == 1

    error = capsys.readouterr().err
    assert "The questions don't match the corpus:" in error
    assert "  a01: no expected source states any of ['ten years']" in error
    assert "Preparing" not in error


@pytest.mark.parametrize(
    ("damage", "message"),
    [
        (
            lambda folder: (folder / "corpus" / "notes.txt").unlink(),
            "There are no corpus sources in corpus.",
        ),
        (lambda folder: (folder / "questions.jsonl").unlink(), "No such file"),
        (
            lambda folder: (folder / "questions.jsonl").write_bytes(b'{"id": "a01"\n'),
            "questions.jsonl line 1: Invalid JSON",
        ),
    ],
    ids=["empty corpus", "no questions file", "unreadable question"],
)
def test_unreadable_evaluation_data_is_reported(
    unit_settings: Settings,
    tmp_path: Path,
    capsys: pytest.CaptureFixture[str],
    damage: Callable[[Path], object],
    message: str,
) -> None:
    arguments = write_evaluation_data(tmp_path, QUESTION)
    damage(tmp_path)

    assert cli.main(["evaluate", *arguments]) == 1

    error = capsys.readouterr().err
    assert "Can't read the evaluation data: " in error
    assert message in error


def test_an_unreachable_database_is_reported(
    unit_settings: Settings, tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    arguments = write_evaluation_data(tmp_path, QUESTION)

    assert cli.main(["evaluate", *arguments]) == 1

    error = capsys.readouterr().err
    assert "Preparing the database unit_tests_eval" in error
    assert "Couldn't prepare the database unit_tests_eval (" in error
    assert "Is PostgreSQL running?" in error
    assert not (tmp_path / "results.json").exists()


@pytest.mark.integration
def test_evaluate_writes_the_results_and_a_summary(
    test_database_url: str,
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    settings = make_settings(database_url=test_database_url, retrieval_min_similarity=0.0)
    model = DescribedModel("ready", "Records are kept for seven years [S1].")
    monkeypatch.setattr(cli, "get_settings", lambda: settings)
    monkeypatch.setattr(cli, "SentenceTransformerEmbeddings", lambda _: HashingEmbeddings())
    monkeypatch.setattr(cli, "OllamaChatModel", lambda _: model)
    arguments = write_evaluation_data(tmp_path, QUESTION)

    assert cli.main(["evaluate", "--with-model", *arguments]) == 0

    output = capsys.readouterr()
    written = (tmp_path / "results.json").read_text(encoding="utf-8")
    report = json.loads(written)
    assert report["run"]["command"] == "python -m app.cli evaluate --with-model"
    assert report["run"]["mode"] == "with_model"
    assert report["environment"]["language_model"] == model.describe()
    assert report["data"]["questions_sha256"] == questions_sha256(tmp_path / "questions.jsonl")
    assert report["answers"]["with_facts"]["all_facts_stated"]["count"] == 1
    # Paths and the database's address say nothing about the results.
    url = make_url(test_database_url)
    assert tmp_path.name not in written
    assert f"{url.host}:{url.port}" not in written
    assert f"Results: {tmp_path / 'results.json'}" in output.out
    database = make_url(cli.evaluation_database_url(settings)).database
    assert f"Preparing the database {database}" in output.err
    assert "Indexed 1 documents into 1 chunks" in output.err


@pytest.mark.integration
def test_evaluate_reports_an_unavailable_embedding_model(
    test_database_url: str,
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    monkeypatch.setattr(cli, "get_settings", lambda: make_settings(database_url=test_database_url))
    monkeypatch.setattr(cli, "SentenceTransformerEmbeddings", lambda _: UnavailableEmbeddings())
    arguments = write_evaluation_data(tmp_path, QUESTION)

    assert cli.main(["evaluate", *arguments]) == 1

    assert "The embedding model isn't available" in capsys.readouterr().err
    assert not (tmp_path / "results.json").exists()
