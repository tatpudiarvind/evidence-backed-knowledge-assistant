from functools import lru_cache
from pathlib import Path

from pydantic import Field, field_validator
from pydantic_settings import BaseSettings, SettingsConfigDict

BACKEND_ROOT = Path(__file__).resolve().parents[2]
# Host runs read the repository's `.env`, the same file Docker Compose uses. In the container
# image this resolves to `/`, where no `.env` exists, so Compose's environment applies instead.
REPOSITORY_ROOT = BACKEND_ROOT.parent
MEBIBYTE = 1024 * 1024


class Settings(BaseSettings):
    app_name: str = "Evidence-backed Knowledge Assistant API"
    app_env: str = "development"
    database_url: str = (
        "postgresql+psycopg://knowledge_assistant:local_dev_only@127.0.0.1:5432/knowledge_assistant"
    )
    # Bounds each connection attempt so readiness fails fast instead of hanging.
    database_connect_timeout_seconds: int = Field(default=3, ge=1)
    cors_origins: list[str] = ["http://localhost:5173"]

    # Local accounts (D-32). Turn registration off once the accounts you need exist.
    registration_enabled: bool = True
    session_lifetime_hours: int = Field(default=12, ge=1, le=720)
    # Set to true whenever the app is served over HTTPS.
    session_cookie_secure: bool = False

    # Uploaded documents (D-33): files live under storage_dir, their metadata in PostgreSQL.
    storage_dir: Path = BACKEND_ROOT / "storage"
    max_upload_bytes: int = Field(default=10 * MEBIBYTE, ge=1, le=100 * MEBIBYTE)
    max_documents_per_workspace: int = Field(default=100, ge=1, le=10_000)

    model_config = SettingsConfigDict(
        env_file=REPOSITORY_ROOT / ".env",
        env_file_encoding="utf-8",
        extra="ignore",
    )

    @field_validator("cors_origins")
    @classmethod
    def _require_explicit_origins(cls, origins: list[str]) -> list[str]:
        # The API accepts cookies from these origins, so a wildcard would let any site use them.
        for origin in origins:
            if not origin.startswith(("http://", "https://")) or "*" in origin:
                raise ValueError("CORS origins must be explicit http:// or https:// origins")
        return origins


@lru_cache
def get_settings() -> Settings:
    return Settings()
