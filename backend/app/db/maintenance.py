"""Creating, migrating, and emptying throwaway databases: the tests' and the evaluation's."""

import re
from collections.abc import Callable
from typing import Any

from sqlalchemy import create_engine, make_url, text
from sqlalchemy.pool import NullPool

from alembic.config import Config
from app.core.config import BACKEND_ROOT

# Every table the migrations create, so emptying them leaves an empty app.
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
_DATABASE_NAME = re.compile(r"[A-Za-z0-9_]+")


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


def create_database_if_missing(database_url: str) -> None:
    """Create the URL's database on its server, connecting through the `postgres` database."""
    database_name = make_url(database_url).database or ""
    if not _DATABASE_NAME.fullmatch(database_name):
        raise ValueError("Database names may only have letters, digits, and underscores.")
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


def empty_tables(database_url: str) -> None:
    """Delete all of the app's data from the database. Only for throwaway databases."""
    engine = create_engine(database_url, poolclass=NullPool)
    try:
        with engine.begin() as connection:
            connection.execute(text(f"TRUNCATE {', '.join(APP_TABLES)} CASCADE"))
    finally:
        engine.dispose()
