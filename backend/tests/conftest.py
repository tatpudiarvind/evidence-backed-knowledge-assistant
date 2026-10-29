"""Test fixtures.

Unit tests need nothing running. Integration tests (marked `integration`) use a real
PostgreSQL database whose name must end in `_test`; it is created and migrated if needed.
Set TEST_DATABASE_URL to point elsewhere. Without a reachable server those tests are skipped,
unless TEST_DATABASE_REQUIRED=1 (as in CI), which makes them fail instead. Tests marked `model`
use the downloaded embedding model and are skipped without it.
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
from sqlalchemy import create_engine, make_url, text
from sqlalchemy.exc import OperationalError
from sqlalchemy.pool import NullPool

from alembic import command
from alembic.config import Config
from app.core.security import PasswordHashing
from app.main import create_app
from app.providers.embeddings import EmbeddingProvider
from app.providers.llm import LanguageModel
from tests.support import HashingEmbeddings, make_settings

BACKEND_ROOT = Path(__file__).resolve().parents[1]
DEFAULT_TEST_DATABASE_URL = "postgresql+psycopg://knowledge_assistant:local_dev_only@127.0.0.1:5432/knowledge_assistant_test"
APP_TABLES = (
    "citations",
    "answers",
    "questions",
    "document_chunks",
    "documents",
    "workspace_memberships",
    "workspaces",
    "user_sessions",
    "users",
)
# The cheapest Argon2 parameters keep tests fast; the app itself uses the library defaults.
CHEAP_PASSWORDS = PasswordHashing(PasswordHasher.from_parameters(profiles.CHEAPEST))

AppFactory = Callable[..., FastAPI]


def alembic_config(connection: Any) -> Config:
    config = Config()
    config.set_main_option("script_location", str(BACKEND_ROOT / "alembic"))
    config.set_main_option("path_separator", "os")
    config.attributes["connection"] = connection
    return config


def run_alembic(database_url: str, action: Callable[[Config], None]) -> None:
    engine = create_engine(database_url, poolclass=NullPool)
    try:
        with engine.begin() as connection:
            action(alembic_config(connection))
    finally:
        engine.dispose()


def _create_database_if_missing(database_url: str, database_name: str) -> None:
    server_engine = create_engine(
        make_url(database_url).set(database="postgres"),
        isolation_level="AUTOCOMMIT",
        poolclass=NullPool,
        connect_args={"connect_timeout": 3},
    )
    try:
        with server_engine.connect() as connection:
            exists = connection.scalar(
                text("SELECT 1 FROM pg_database WHERE datname = :name"), {"name": database_name}
            )
            if not exists:
                # The name was checked against a strict pattern, so quoting it is enough.
                connection.execute(text(f'CREATE DATABASE "{database_name}"'))
    finally:
        server_engine.dispose()


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
        _create_database_if_missing(database_url, database_name)
        run_alembic(database_url, lambda config: command.upgrade(config, "head"))
    except OperationalError as error:
        if os.environ.get("TEST_DATABASE_REQUIRED") == "1":
            raise
        pytest.skip(f"PostgreSQL test database unavailable ({type(error).__name__})")
    return database_url


@pytest.fixture
def database_url(test_database_url: str) -> str:
    """The test database, emptied before each test."""
    engine = create_engine(test_database_url, poolclass=NullPool)
    try:
        with engine.begin() as connection:
            connection.execute(text(f"TRUNCATE {', '.join(APP_TABLES)} CASCADE"))
    finally:
        engine.dispose()
    return test_database_url


@pytest.fixture
def storage_dir(tmp_path: Path) -> Path:
    return tmp_path / "storage"


@pytest.fixture
def make_app(storage_dir: Path) -> Iterator[AppFactory]:
    """Builds apps that don't touch a database unless given one.

    They embed text with `HashingEmbeddings` unless given another provider, have no language
    model unless given one, and their background threads stay off unless their settings turn
    them on.
    """
    apps: list[FastAPI] = []

    def factory(
        *,
        embeddings: EmbeddingProvider | None = None,
        language_model: LanguageModel | None = None,
        **overrides: Any,
    ) -> FastAPI:
        overrides.setdefault("storage_dir", storage_dir)
        app = create_app(
            make_settings(**overrides),
            passwords=CHEAP_PASSWORDS,
            embeddings=embeddings or HashingEmbeddings(),
            language_model=language_model,
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
