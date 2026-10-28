"""Migrations run both ways and produce exactly the tables the models describe (P2-02, P2-03)."""

import pytest
from sqlalchemy import create_engine, inspect
from sqlalchemy.pool import NullPool

from alembic import command
from alembic.autogenerate import compare_metadata
from alembic.migration import MigrationContext
from alembic.script import ScriptDirectory
from app.db.base import Base
from tests.conftest import APP_TABLES, alembic_config, run_alembic

pytestmark = pytest.mark.integration


def test_there_is_a_single_migration_head() -> None:
    script = ScriptDirectory.from_config(alembic_config(connection=None))

    assert len(script.get_heads()) == 1


def test_migrations_downgrade_and_upgrade_and_match_the_models(database_url: str) -> None:
    run_alembic(database_url, lambda config: command.downgrade(config, "base"))
    run_alembic(database_url, lambda config: command.upgrade(config, "head"))

    engine = create_engine(database_url, poolclass=NullPool)
    try:
        with engine.connect() as connection:
            context = MigrationContext.configure(connection, opts={"compare_type": True})
            differences = compare_metadata(context, Base.metadata)
            tables = set(inspect(connection).get_table_names())
    finally:
        engine.dispose()

    assert differences == []
    assert set(APP_TABLES) <= tables
