"""The maintenance command line (P3-05), with stand-ins for the download and the model."""

import sys
import types
from pathlib import Path
from typing import Any

import pytest

from app import cli
from app.core.config import Settings
from app.domain.indexing import EMBEDDING_DIMENSION
from app.providers.embeddings import EmbeddingUnavailableError
from tests.support import make_settings


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
    assert "download-embedding-model" in capsys.readouterr().err
