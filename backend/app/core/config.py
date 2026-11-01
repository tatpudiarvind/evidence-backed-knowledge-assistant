import ipaddress
from functools import lru_cache
from pathlib import Path
from typing import Literal, Self
from urllib.parse import urlsplit

from pydantic import Field, SecretStr, field_validator, model_validator
from pydantic_settings import BaseSettings, SettingsConfigDict

from app.domain.retrieval import RetrievalMode

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


def is_loopback_host(hostname: str) -> bool:
    """Whether a host name is this computer: `localhost` or a loopback address."""
    if hostname.lower().rstrip(".") == "localhost":
        return True
    try:
        return ipaddress.ip_address(hostname).is_loopback
    except ValueError:
        return False


class Settings(BaseSettings):
    app_name: str = "Evidence-backed Knowledge Assistant API"
    app_env: str = "development"
    database_url: str = (
        "postgresql+psycopg://knowledge_assistant:local_dev_only@127.0.0.1:5432/knowledge_assistant"
    )
    # Bounds each connection attempt so readiness fails fast instead of hanging.
    database_connect_timeout_seconds: int = Field(default=3, ge=1)
    cors_origins: list[str] = ["http://localhost:5173"]

    # Logs and metrics (Phase 5). The API logs to standard error, as text or as one JSON object
    # per line. DEBUG adds the details of unexpected indexing errors, which can quote documents.
    log_format: Literal["text", "json"] = "text"
    log_level: Literal["DEBUG", "INFO", "WARNING", "ERROR"] = "INFO"
    # Serves the metrics at /metrics, where anyone who can reach the API can read them.
    metrics_enabled: bool = False

    # Local accounts (D-32). Turn registration off once the accounts you need exist.
    registration_enabled: bool = True
    session_lifetime_hours: int = Field(default=12, ge=1, le=720)
    # Set to true whenever the app is served over HTTPS.
    session_cookie_secure: bool = False

    # Rate limits (Phase 5), counted in the API process's memory and reset when it restarts.
    # Sign-in and registration attempts are counted per network address, questions per account.
    rate_limits_enabled: bool = True
    sign_in_attempts_per_minute: int = Field(default=10, ge=1, le=10_000)
    registration_attempts_per_hour: int = Field(default=10, ge=1, le=10_000)
    questions_per_minute: int = Field(default=10, ge=1, le=10_000)

    # Uploaded documents (D-33): files live under storage_dir, their metadata in PostgreSQL.
    storage_dir: Path = BACKEND_ROOT / "storage"
    max_upload_bytes: int = Field(default=10 * MEBIBYTE, ge=1, le=100 * MEBIBYTE)
    max_documents_per_workspace: int = Field(default=100, ge=1, le=10_000)
    # How long an upload may take to arrive, so a stalled one can't hold its connection forever.
    upload_timeout_seconds: int = Field(default=120, ge=1, le=3600)

    indexing_runner: Literal["embedded", "worker"] = "embedded"
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
    # "openai_compatible" (Phase 9) uses any server that speaks the OpenAI chat API, set by
    # LLM_BASE_URL, LLM_MODEL, and LLM_API_KEY. A server that isn't on this computer is a hosted
    # provider: it receives the question and passages, so it's off unless chosen (D-84).
    llm_provider: Literal["ollama", "openai_compatible", "none"] = "ollama"
    llm_base_url: str | None = None
    llm_model: str | None = None
    llm_api_key: SecretStr | None = None
    # Vendors differ on the name of the parameter that limits a reply's length.
    llm_token_limit_parameter: Literal["max_tokens", "max_completion_tokens"] = "max_tokens"
    # Retries after a 429, a 5xx, or a lost connection; waits grow from one second.
    llm_max_retries: int = Field(default=2, ge=0, le=5)
    # Calls to a hosted provider per UTC day, counted in PostgreSQL across all API processes.
    # Past it, answers list the passages instead of calling the provider.
    llm_daily_call_limit: int = Field(default=200, ge=1, le=1_000_000)
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
    # How passages are found (Phase 7, D-81): see app/domain/retrieval.py. "vector" is the
    # search of Phases 4 to 6.
    retrieval_mode: RetrievalMode = "vector"
    # How many passages each search returns for fusion, in the hybrid modes.
    retrieval_candidates: int = Field(default=20, ge=1, le=100)
    # The k in reciprocal rank fusion's 1 / (k + rank), as in the paper that introduced it.
    rrf_k: int = Field(default=60, ge=1, le=1000)
    # The cross-encoder of "hybrid_rerank", kept in EMBEDDING_MODEL_DIR. Download it once with
    # `python -m app.cli download-reranker-model`. It was trained on MS MARCO, whose terms allow
    # non-commercial research use only (D-81); BAAI/bge-reranker-base is MIT-licensed.
    reranker_model_name: str = "cross-encoder/ms-marco-MiniLM-L6-v2"
    reranker_model_revision: str = Field(
        default="233902d25c440f23af6f7d6e94d2946bac0bee0a", pattern=r"^[0-9a-f]{40}$"
    )
    # The most passage text the model is shown for one question, in characters.
    answer_context_characters: int = Field(default=6000, ge=1000, le=50_000)
    # A background thread in the API process deletes questions three days after they're asked.
    question_cleanup_enabled: bool = True

    # Sign-in (Phase 10). "local" is the accounts above. "oidc" signs in through one OpenID
    # Connect provider and turns password sign-in and registration off; "both" allows either.
    # The API is the provider's client, so the client secret never reaches the browser (D-85).
    auth_mode: Literal["local", "oidc", "both"] = "local"
    oidc_issuer: str | None = None
    oidc_client_id: str | None = None
    oidc_client_secret: SecretStr | None = None
    # The callback's full address, as registered at the provider. It must be on the address
    # people use for the web app, so the session cookie is set for the right site.
    oidc_redirect_uri: str | None = None
    oidc_scopes: str = "openid email profile"
    oidc_provider_name: str | None = Field(default=None, max_length=40)
    oidc_timeout_seconds: int = Field(default=10, ge=1, le=60)

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

    @field_validator("log_level", mode="before")
    @classmethod
    def _upper_case_log_level(cls, level: object) -> object:
        return level.upper() if isinstance(level, str) else level

    @field_validator("ollama_base_url")
    @classmethod
    def _check_ollama_url(cls, url: str) -> str:
        if not url.startswith(("http://", "https://")):
            raise ValueError("OLLAMA_BASE_URL must be an http:// or https:// URL")
        return url.rstrip("/")

    @field_validator(
        "llm_base_url",
        "llm_model",
        "oidc_issuer",
        "oidc_client_id",
        "oidc_client_secret",
        "oidc_redirect_uri",
        "oidc_provider_name",
        mode="before",
    )
    @classmethod
    def _blank_is_unset(cls, value: object) -> object:
        return None if isinstance(value, str) and not value.strip() else value

    @model_validator(mode="after")
    def _check_oidc(self) -> Self:
        if self.auth_mode == "local":
            return self
        secret = self.oidc_client_secret.get_secret_value() if self.oidc_client_secret else ""
        if not (
            self.oidc_issuer
            and self.oidc_client_id
            and secret
            and self.oidc_redirect_uri
            and self.oidc_provider_name
        ):
            raise ValueError(
                "AUTH_MODE other than local needs OIDC_ISSUER, OIDC_CLIENT_ID, "
                "OIDC_CLIENT_SECRET, OIDC_REDIRECT_URI, and OIDC_PROVIDER_NAME"
            )
        for name, url in (
            ("OIDC_ISSUER", self.oidc_issuer),
            ("OIDC_REDIRECT_URI", self.oidc_redirect_uri),
        ):
            parts = urlsplit(url)
            if parts.scheme not in ("http", "https") or not parts.hostname or parts.username:
                raise ValueError(f"{name} must be an http:// or https:// URL without a login")
            if parts.fragment:
                raise ValueError(f"{name} can't have a fragment")
            # Codes and tokens must not cross the network unencrypted.
            if parts.scheme != "https" and not is_loopback_host(parts.hostname):
                raise ValueError(f"{name} must use https:// unless it's on this computer")
        if "openid" not in self.oidc_scopes.split():
            self.oidc_scopes = f"openid {self.oidc_scopes}".strip()
        return self

    @property
    def password_sign_in_enabled(self) -> bool:
        return self.auth_mode in ("local", "both")

    @property
    def oidc_enabled(self) -> bool:
        return self.auth_mode in ("oidc", "both")

    @model_validator(mode="after")
    def _check_openai_compatible(self) -> Self:
        if self.llm_provider != "openai_compatible":
            return self
        if not self.llm_base_url or not self.llm_model:
            raise ValueError("LLM_BASE_URL and LLM_MODEL are required for openai_compatible")
        parts = urlsplit(self.llm_base_url)
        if parts.scheme not in ("http", "https") or not parts.hostname or parts.username:
            raise ValueError("LLM_BASE_URL must be an http:// or https:// URL without a login")
        self.llm_base_url = self.llm_base_url.rstrip("/")
        if not is_loopback_host(parts.hostname):
            # A key or a question must not cross the network unencrypted, or without a key.
            if parts.scheme != "https":
                raise ValueError("LLM_BASE_URL must use https:// unless it's on this computer")
            if self.llm_api_key is None or not self.llm_api_key.get_secret_value():
                raise ValueError("LLM_API_KEY is required for a server that isn't on this computer")
        return self

    @property
    def llm_is_hosted(self) -> bool:
        """Whether answers are written by a server that isn't on this computer."""
        if self.llm_provider != "openai_compatible" or not self.llm_base_url:
            return False
        hostname = urlsplit(self.llm_base_url).hostname
        return hostname is None or not is_loopback_host(hostname)

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

    @model_validator(mode="after")
    def _check_retrieval_candidates(self) -> Self:
        # The hybrid modes keep RETRIEVAL_TOP_K of the candidates, so each search needs as many.
        if self.retrieval_candidates < self.retrieval_top_k:
            raise ValueError("RETRIEVAL_CANDIDATES must be at least RETRIEVAL_TOP_K")
        return self


@lru_cache
def get_settings() -> Settings:
    return Settings()
