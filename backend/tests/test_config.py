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
        {"llm_timeout_seconds": 0},
        {"llm_timeout_seconds": 601},
        {"ollama_context_tokens": 1023},
        {"ollama_context_tokens": 131_073},
        {"retrieval_top_k": 0},
        {"retrieval_top_k": 21},
        {"retrieval_min_similarity": -0.01},
        {"retrieval_min_similarity": 1.01},
        {"retrieval_candidates": 101},
        {"rrf_k": 0},
        {"rrf_k": 1001},
        {"answer_context_characters": 999},
        {"answer_context_characters": 50_001},
        {"sign_in_attempts_per_minute": 0},
        {"registration_attempts_per_hour": 0},
        {"questions_per_minute": 0},
        {"questions_per_minute": 10_001},
        {"upload_timeout_seconds": 0},
        {"upload_timeout_seconds": 3601},
    ],
)
def test_limits_must_stay_in_range(overrides: dict[str, float]) -> None:
    with pytest.raises(ValidationError):
        make_settings(**overrides)


def test_rate_limits_are_on_by_default() -> None:
    assert config.Settings.model_fields["rate_limits_enabled"].default is True


def test_logs_are_text_at_info_and_metrics_are_not_served_by_default() -> None:
    fields = config.Settings.model_fields
    assert fields["log_format"].default == "text"
    assert fields["log_level"].default == "INFO"
    assert fields["metrics_enabled"].default is False


@pytest.mark.parametrize("level", ["debug", "Warning", "ERROR"])
def test_log_levels_are_accepted_in_any_case(level: str) -> None:
    assert make_settings(log_level=level).log_level == level.upper()


@pytest.mark.parametrize(
    "overrides",
    [{"log_level": "TRACE"}, {"log_level": ""}, {"log_format": "xml"}, {"log_format": "JSON"}],
)
def test_unknown_log_settings_are_rejected(overrides: dict[str, str]) -> None:
    with pytest.raises(ValidationError):
        make_settings(**overrides)


def test_chunk_overlap_is_at_most_a_quarter_of_the_chunk_size() -> None:
    settings = make_settings(chunk_size_characters=1000, chunk_overlap_characters=250)
    assert settings.chunk_overlap_characters == 250

    with pytest.raises(ValidationError, match="CHUNK_OVERLAP_CHARACTERS"):
        make_settings(chunk_size_characters=1000, chunk_overlap_characters=251)


@pytest.mark.parametrize("setting", ["embedding_model_revision", "reranker_model_revision"])
@pytest.mark.parametrize(
    "revision", ["main", "5c38ec7", "5C38EC7C405EC4B44B94CC5A9BB96E735B38267A"]
)
def test_the_model_revision_must_be_a_full_commit_hash(setting: str, revision: str) -> None:
    with pytest.raises(ValidationError):
        make_settings(**{setting: revision})


def test_search_is_by_meaning_by_default() -> None:
    fields = config.Settings.model_fields

    assert fields["retrieval_mode"].default == "vector"
    assert (fields["retrieval_candidates"].default, fields["rrf_k"].default) == (20, 60)
    assert fields["reranker_model_name"].default == "cross-encoder/ms-marco-MiniLM-L6-v2"
    assert fields["reranker_model_revision"].default == "233902d25c440f23af6f7d6e94d2946bac0bee0a"


@pytest.mark.parametrize("mode", ["hybrid", "hybrid_rerank"])
def test_the_hybrid_modes_are_accepted(mode: str) -> None:
    assert make_settings(retrieval_mode=mode).retrieval_mode == mode


@pytest.mark.parametrize("mode", ["bm25", "", "HYBRID", "hybrid-rerank"])
def test_only_known_retrieval_modes_are_accepted(mode: str) -> None:
    with pytest.raises(ValidationError):
        make_settings(retrieval_mode=mode)


@pytest.mark.parametrize("mode", ["vector", "hybrid"])
def test_each_search_finds_at_least_as_many_passages_as_are_kept(mode: str) -> None:
    settings = make_settings(retrieval_mode=mode, retrieval_top_k=4, retrieval_candidates=4)
    assert settings.retrieval_candidates == 4

    with pytest.raises(ValidationError, match="RETRIEVAL_CANDIDATES"):
        make_settings(retrieval_mode=mode, retrieval_top_k=4, retrieval_candidates=3)


def test_answers_come_from_local_ollama_by_default() -> None:
    fields = config.Settings.model_fields

    assert fields["llm_provider"].default == "ollama"
    assert fields["ollama_base_url"].default == "http://127.0.0.1:11434"


@pytest.mark.parametrize("provider", ["openai", "", "OLLAMA"])
def test_only_known_language_model_providers_are_accepted(provider: str) -> None:
    with pytest.raises(ValidationError):
        make_settings(llm_provider=provider)


@pytest.mark.parametrize("url", ["127.0.0.1:11434", "ftp://127.0.0.1", "file:///tmp/x", ""])
def test_the_ollama_address_must_be_a_web_address(url: str) -> None:
    with pytest.raises(ValidationError, match="OLLAMA_BASE_URL"):
        make_settings(ollama_base_url=url)


def test_a_trailing_slash_is_removed_from_the_ollama_address() -> None:
    settings = make_settings(ollama_base_url="http://ollama.internal:11434/")

    assert settings.ollama_base_url == "http://ollama.internal:11434"


def test_the_passages_must_fit_in_the_models_context_window() -> None:
    # 6000 characters is about 2000 tokens, leaving 1792 for the rules, question, and answer.
    fits = make_settings(llm_provider="ollama", answer_context_characters=6000)
    assert fits.ollama_context_tokens == 4096

    with pytest.raises(ValidationError, match="ANSWER_CONTEXT_CHARACTERS"):
        make_settings(llm_provider="ollama", answer_context_characters=7000)

    larger = make_settings(
        llm_provider="ollama", answer_context_characters=7000, ollama_context_tokens=8192
    )
    assert larger.answer_context_characters == 7000
    # Without a model, the passages are shown to no model, so any length is fine.
    assert make_settings(answer_context_characters=50_000).llm_provider == "none"


OIDC = {
    "oidc_issuer": "https://id.example.com/realms/eka",
    "oidc_client_id": "eka",
    "oidc_client_secret": "secret",
    "oidc_redirect_uri": "https://app.example.com/api/v1/auth/oidc/callback",
    "oidc_provider_name": "Example ID",
}


def test_local_mode_needs_no_provider_settings() -> None:
    settings = make_settings()

    assert settings.password_sign_in_enabled
    assert not settings.oidc_enabled


@pytest.mark.parametrize("missing", sorted(OIDC))
def test_a_provider_mode_needs_every_provider_setting(missing: str) -> None:
    values = {key: value for key, value in OIDC.items() if key != missing}

    with pytest.raises(ValidationError, match="OIDC_ISSUER"):
        make_settings(auth_mode="oidc", **values)


def test_the_modes_say_which_sign_ins_are_on() -> None:
    both = make_settings(auth_mode="both", **OIDC)
    oidc = make_settings(auth_mode="oidc", **OIDC)

    assert both.password_sign_in_enabled and both.oidc_enabled
    assert not oidc.password_sign_in_enabled and oidc.oidc_enabled


@pytest.mark.parametrize(
    "name, value",
    [
        ("oidc_issuer", "http://id.example.com/realms/eka"),
        ("oidc_redirect_uri", "http://app.example.com/callback"),
        ("oidc_issuer", "https://user:pass@id.example.com"),
        ("oidc_redirect_uri", "https://app.example.com/callback#frag"),
        ("oidc_issuer", "ftp://id.example.com"),
    ],
)
def test_provider_addresses_must_be_safe(name: str, value: str) -> None:
    with pytest.raises(ValidationError):
        make_settings(auth_mode="oidc", **{**OIDC, name: value})


def test_a_provider_on_this_computer_may_use_http() -> None:
    settings = make_settings(
        auth_mode="oidc",
        **{**OIDC, "oidc_issuer": "http://localhost:8081/realms/eka"},
    )

    assert settings.oidc_enabled


def test_the_openid_scope_is_always_asked_for() -> None:
    settings = make_settings(auth_mode="oidc", oidc_scopes="email", **OIDC)

    assert settings.oidc_scopes.split() == ["openid", "email"]


def test_blank_provider_settings_count_as_unset() -> None:
    settings = make_settings(oidc_issuer="", oidc_client_secret="")

    assert settings.oidc_issuer is None
    assert settings.oidc_client_secret is None
