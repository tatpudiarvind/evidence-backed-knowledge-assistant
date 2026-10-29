import pytest
from pydantic import ValidationError

from app.core import config
from tests.support import make_settings


def test_env_file_is_the_repository_root_env() -> None:
    env_file = config.Settings.model_config["env_file"]

    assert env_file == config.BACKEND_ROOT.parent / ".env"
    assert (config.BACKEND_ROOT / "app" / "main.py").is_file()


def test_documents_are_stored_under_the_backend_by_default() -> None:
    assert make_settings().storage_dir == config.BACKEND_ROOT / "storage"


def test_the_embedding_model_is_kept_under_the_backend_by_default() -> None:
    assert make_settings().embedding_model_dir == config.BACKEND_ROOT / "models"


@pytest.mark.parametrize("origin", ["*", "http://*.example.com", "localhost:5173", "ftp://x"])
def test_cors_origins_must_be_explicit(origin: str) -> None:
    with pytest.raises(ValidationError):
        make_settings(cors_origins=[origin])


def test_explicit_cors_origins_are_accepted() -> None:
    origins = ["http://localhost:5173", "https://assistant.example.org"]

    assert make_settings(cors_origins=origins).cors_origins == origins


@pytest.mark.parametrize(
    "overrides",
    [
        {"max_upload_bytes": 0},
        {"max_upload_bytes": 101 * 1024 * 1024},
        {"max_documents_per_workspace": 0},
        {"session_lifetime_hours": 0},
        {"session_lifetime_hours": 721},
        {"chunk_size_characters": 199, "chunk_overlap_characters": 0},
        {"chunk_size_characters": 4001},
        {"chunk_overlap_characters": -1},
        {"max_document_pages": 0},
        {"max_document_pages": 10_001},
        {"max_document_characters": 999},
        {"parse_timeout_seconds": 0},
        {"embedding_batch_size": 0},
        {"embedding_batch_size": 513},
    ],
)
def test_limits_must_stay_in_range(overrides: dict[str, int]) -> None:
    with pytest.raises(ValidationError):
        make_settings(**overrides)


def test_chunk_overlap_is_at_most_a_quarter_of_the_chunk_size() -> None:
    settings = make_settings(chunk_size_characters=1000, chunk_overlap_characters=250)
    assert settings.chunk_overlap_characters == 250

    with pytest.raises(ValidationError, match="CHUNK_OVERLAP_CHARACTERS"):
        make_settings(chunk_size_characters=1000, chunk_overlap_characters=251)


@pytest.mark.parametrize(
    "revision", ["main", "5c38ec7", "5C38EC7C405EC4B44B94CC5A9BB96E735B38267A"]
)
def test_the_model_revision_must_be_a_full_commit_hash(revision: str) -> None:
    with pytest.raises(ValidationError):
        make_settings(embedding_model_revision=revision)
