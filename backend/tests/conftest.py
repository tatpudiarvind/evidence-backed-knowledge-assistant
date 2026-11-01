"""Test fixtures.

Unit tests need nothing running. Integration tests (marked `integration`) use a real
PostgreSQL database whose name must end in `_test`; it is created and migrated if needed.
Set TEST_DATABASE_URL to point elsewhere. Without a reachable server those tests are skipped,
unless TEST_DATABASE_REQUIRED=1 (as in CI), which makes them fail instead. Tests marked `model`
use a downloaded model, the embedding model or the reranker, and are skipped without it.
"""

import os
import re
from collections.abc import Callable, Iterator
from pathlib import Path
from typing import Any

import pytest
from argon2 import PasswordHasher, profiles
from fastapi import FastAPI
from fastapi.testclient import TestClient
from sqlalchemy import make_url
from sqlalchemy.exc import OperationalError

from alembic import command
from app.core.security import PasswordHashing
from app.db.maintenance import create_database_if_missing, empty_tables, run_alembic
from app.factory import create_app
from app.providers.embeddings import EmbeddingProvider
from app.providers.llm import LanguageModel
from app.providers.rerankers import Reranker
from tests.support import (
    HashingEmbeddings,
    Workspace,
    create_workspace,
    make_settings,
    register,
)

DEFAULT_TEST_DATABASE_URL = "postgresql+psycopg://knowledge_assistant:local_dev_only@127.0.0.1:5432/knowledge_assistant_test"
# The cheapest Argon2 parameters keep tests fast; the app itself uses the library defaults.
CHEAP_PASSWORDS = PasswordHashing(PasswordHasher.from_parameters(profiles.CHEAPEST))
# What configure_hugging_face sets for the process.
HF_VARIABLES = (
    "HF_HOME",
    "HF_HUB_DISABLE_TELEMETRY",
    "HF_HUB_DISABLE_XET",
    "HF_HUB_DISABLE_SYMLINKS_WARNING",
    "HF_HUB_OFFLINE",
    "HF_HUB_DISABLE_PROGRESS_BARS",
)

AppFactory = Callable[..., FastAPI]


@pytest.fixture
def clean_hf_environment(monkeypatch: pytest.MonkeyPatch) -> None:
    """Remove Hugging Face settings for one test, and put back afterwards whatever was there."""
    for name in HF_VARIABLES:
        # Setting first makes monkeypatch restore the variable, even if it didn't exist.
        monkeypatch.setenv(name, "")
        monkeypatch.delenv(name)


@pytest.fixture(scope="session")
def test_database_url() -> str:
    database_url = os.environ.get("TEST_DATABASE_URL", DEFAULT_TEST_DATABASE_URL)
    database_name = make_url(database_url).database or ""
    if not re.fullmatch(r"[A-Za-z0-9_]+_test", database_name):
        pytest.fail(
            "TEST_DATABASE_URL must name a database ending in _test; "
            "integration tests delete all of its data."
        )
    try:
        create_database_if_missing(database_url)
        run_alembic(database_url, lambda config: command.upgrade(config, "head"))
    except OperationalError as error:
        if os.environ.get("TEST_DATABASE_REQUIRED") == "1":
            raise
        pytest.skip(f"PostgreSQL test database unavailable ({type(error).__name__})")
    return database_url


@pytest.fixture
def database_url(test_database_url: str) -> str:
    """The test database, emptied before each test."""
    empty_tables(test_database_url)
    return test_database_url


@pytest.fixture
def storage_dir(tmp_path: Path) -> Path:
    return tmp_path / "storage"


@pytest.fixture
def make_app(storage_dir: Path) -> Iterator[AppFactory]:
    """Builds apps that don't touch a database unless given one.

    They embed text with `HashingEmbeddings` unless given another provider, have no language
    model unless given one, and their background threads stay off unless their settings turn
    them on. In `hybrid_rerank` mode without a given reranker, they get the real one, which
    loads on first use.
    """
    apps: list[FastAPI] = []

    def factory(
        *,
        embeddings: EmbeddingProvider | None = None,
        language_model: LanguageModel | None = None,
        reranker: Reranker | None = None,
        **overrides: Any,
    ) -> FastAPI:
        overrides.setdefault("storage_dir", storage_dir)
        app = create_app(
            make_settings(**overrides),
            passwords=CHEAP_PASSWORDS,
            embeddings=embeddings or HashingEmbeddings(),
            language_model=language_model,
            reranker=reranker,
        )
        apps.append(app)
        return app

    yield factory
    for app in apps:
        app.state.ingestion_worker.stop()
        app.state.question_cleanup.stop()
        app.state.engine.dispose()


@pytest.fixture
def make_db_app(make_app: AppFactory, database_url: str) -> AppFactory:
    """Builds apps connected to the emptied test database."""

    def factory(**overrides: Any) -> FastAPI:
        return make_app(database_url=database_url, **overrides)

    return factory


@pytest.fixture
def db_app(make_db_app: AppFactory) -> FastAPI:
    return make_db_app()


@pytest.fixture
def make_client() -> Callable[[FastAPI], TestClient]:
    """A new client per user: each keeps its own cookies."""

    def factory(app: FastAPI) -> TestClient:
        return TestClient(app, raise_server_exceptions=False)

    return factory


@pytest.fixture
def make_workspace(
    make_db_app: AppFactory, make_client: Callable[[FastAPI], TestClient]
) -> Callable[..., Workspace]:
    """Builds a database-backed app, signs a new user in, and gives them a workspace."""

    def factory(**overrides: Any) -> Workspace:
        app = make_db_app(**overrides)
        client = make_client(app)
        assert register(client).status_code == 201
        return Workspace(app, client, create_workspace(client)["id"])

    return factory
