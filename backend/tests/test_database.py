from typing import Any

import pytest
from pydantic import ValidationError

from app.core import database
from app.core.config import Settings


def test_engine_bounds_connection_attempts(monkeypatch) -> None:
    captured: dict[str, Any] = {}

    def fake_create_engine(url: str, **kwargs: Any) -> object:
        captured["url"] = url
        captured.update(kwargs)
        return object()

    settings = Settings(_env_file=None, database_connect_timeout_seconds=4)
    monkeypatch.setattr(database, "get_settings", lambda: settings)
    monkeypatch.setattr(database, "create_engine", fake_create_engine)
    database.get_engine.cache_clear()
    try:
        database.get_engine()
    finally:
        database.get_engine.cache_clear()

    assert captured["url"] == settings.database_url
    assert captured["pool_pre_ping"] is True
    assert captured["connect_args"] == {"connect_timeout": 4}


def test_connect_timeout_cannot_disable_the_limit() -> None:
    # PostgreSQL treats a timeout of 0 as "wait forever".
    with pytest.raises(ValidationError):
        Settings(_env_file=None, database_connect_timeout_seconds=0)
