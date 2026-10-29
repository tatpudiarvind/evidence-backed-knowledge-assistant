from functools import lru_cache
from pathlib import Path
from typing import Literal, Self

from pydantic import Field, field_validator, model_validator
from pydantic_settings import BaseSettings, SettingsConfigDict

BACKEND_ROOT = Path(__file__).resolve().parents[2]
# Host runs read the repository's `.env`, the same file Docker Compose uses. In the container
# image this resolves to `/`, where no `.env` exists, so Compose's environment applies instead.
REPOSITORY_ROOT = BACKEND_ROOT.parent
MEBIBYTE = 1024 * 1024
# The longest answer a language model may write, in tokens.
MAX_ANSWER_TOKENS = 768
# Room kept in the model's context for its rules, the question, and the answer, in tokens.
_PROMPT_RESERVED_TOKENS = MAX_ANSWER_TOKENS + 1024
# A cautious estimate for passage text; English averages about 4 characters per token.
_CHARACTERS_PER_TOKEN = 3


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

    # Indexing (Phase 3). A background thread in the API process indexes queued documents;
    # turn it off to keep uploads queued, as the tests do.
    ingestion_worker_enabled: bool = True
    chunk_size_characters: int = Field(default=1000, ge=200, le=4000)
    chunk_overlap_characters: int = Field(default=150, ge=0)
    max_document_pages: int = Field(default=500, ge=1, le=10_000)
    max_document_characters: int = Field(default=2_000_000, ge=1_000, le=50_000_000)
    # Checked between pages and paragraphs, so a single slow page can run past it.
    parse_timeout_seconds: int = Field(default=120, ge=1, le=3600)

    # The local embedding model (D-34). Download it once with
    # `python -m app.cli download-embedding-model`; indexing itself never downloads anything.
    embedding_model_name: str = "BAAI/bge-small-en-v1.5"
    # A Hugging Face commit, so every machine runs exactly the same model files.
    embedding_model_revision: str = Field(
        default="5c38ec7c405ec4b44b94cc5a9bb96e735b38267a", pattern=r"^[0-9a-f]{40}$"
    )
    embedding_model_dir: Path = BACKEND_ROOT / "models"
    embedding_batch_size: int = Field(default=32, ge=1, le=512)
    # The model card's instruction for short search queries; documents get no prefix.
    embedding_query_prefix: str = "Represent this sentence for searching relevant passages: "

    # Answers (Phase 4). With "ollama", a local Ollama server writes answers from the passages
    # found for each question. With "none", or while that server doesn't reply, answers list
    # the passages instead.
    llm_provider: Literal["ollama", "none"] = "ollama"
    ollama_base_url: str = "http://127.0.0.1:11434"
    ollama_model: str = "qwen3:4b-instruct-2507-q4_K_M"
    # A local model on an ordinary computer can take a minute or more to answer.
    llm_timeout_seconds: int = Field(default=120, ge=1, le=600)
    # The model's context window, in tokens; the rules, passages, question, and answer share it.
    ollama_context_tokens: int = Field(default=4096, ge=1024, le=131_072)
    # How many of the passages closest to a question are considered. Set by the Phase 5
    # evaluation's rule (docs/evaluation/): on its questions, more passages found no more facts.
    retrieval_top_k: int = Field(default=4, ge=1, le=20)
    # Passages less similar to the question than this don't count as evidence. Set by the
    # evaluation's rule; it keeps out off-topic questions, not on-topic ones nothing answers.
    retrieval_min_similarity: float = Field(default=0.5, ge=0.0, le=1.0)
    # The most passage text the model is shown for one question, in characters.
    answer_context_characters: int = Field(default=6000, ge=1000, le=50_000)
    # A background thread in the API process deletes questions three days after they're asked.
    question_cleanup_enabled: bool = True

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

    @field_validator("ollama_base_url")
    @classmethod
    def _check_ollama_url(cls, url: str) -> str:
        if not url.startswith(("http://", "https://")):
            raise ValueError("OLLAMA_BASE_URL must be an http:// or https:// URL")
        return url.rstrip("/")

    @model_validator(mode="after")
    def _check_chunk_overlap(self) -> Self:
        # Each chunk must start well after the previous one, or indexing would barely advance.
        if self.chunk_overlap_characters * 4 > self.chunk_size_characters:
            raise ValueError(
                "CHUNK_OVERLAP_CHARACTERS must be at most a quarter of CHUNK_SIZE_CHARACTERS"
            )
        return self

    @model_validator(mode="after")
    def _check_answer_context(self) -> Self:
        # A prompt longer than the context window gets cut, which could drop the model's rules.
        needed = self.answer_context_characters // _CHARACTERS_PER_TOKEN + _PROMPT_RESERVED_TOKENS
        if self.llm_provider == "ollama" and needed > self.ollama_context_tokens:
            raise ValueError(
                "ANSWER_CONTEXT_CHARACTERS is too large for OLLAMA_CONTEXT_TOKENS: lower the "
                "first or raise the second"
            )
        return self


@lru_cache
def get_settings() -> Settings:
    return Settings()
