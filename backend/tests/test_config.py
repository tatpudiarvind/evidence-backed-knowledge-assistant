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
    ],
)
def test_limits_must_stay_in_range(overrides: dict[str, int]) -> None:
    with pytest.raises(ValidationError):
        make_settings(**overrides)
