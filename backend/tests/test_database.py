from typing import Any

import pytest
from pydantic import ValidationError

from app.core import database
from app.core.config import Settings
from tests.support import make_settings


def test_engine_bounds_connection_attempts_and_hides_parameters(monkeypatch) -> None:
    captured: dict[str, Any] = {}

    def fake_create_engine(url: str, **kwargs: Any) -> object:
        captured["url"] = url
        captured.update(kwargs)
        return object()

    settings = make_settings(database_connect_timeout_seconds=4)
    monkeypatch.setattr(database, "create_engine", fake_create_engine)

    database.create_database_engine(settings)

    assert captured["url"] == settings.database_url
    assert captured["pool_pre_ping"] is True
    assert captured["hide_parameters"] is True
    assert captured["connect_args"] == {"connect_timeout": 4}


def test_connect_timeout_cannot_disable_the_limit() -> None:
    # PostgreSQL treats a timeout of 0 as "wait forever".
    with pytest.raises(ValidationError):
        Settings(_env_file=None, database_connect_timeout_seconds=0)


def test_session_factory_keeps_objects_readable_after_commit() -> None:
    engine = database.create_database_engine(make_settings())
    try:
        factory = database.create_session_factory(engine)
        assert factory.kw["expire_on_commit"] is False
    finally:
        engine.dispose()
