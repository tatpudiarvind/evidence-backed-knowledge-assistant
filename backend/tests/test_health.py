from collections.abc import Callable

from fastapi import FastAPI
from fastapi.testclient import TestClient
from sqlalchemy.exc import SQLAlchemyError

from app.api import health


def test_live_reports_process_is_running(make_app: Callable[..., FastAPI]) -> None:
    response = TestClient(make_app()).get("/health/live")

    assert response.status_code == 200
    assert response.json() == {"status": "ok"}


def test_ready_reports_database_available(make_app, monkeypatch) -> None:
    app = make_app()
    checked = []
    monkeypatch.setattr(health, "check_database", checked.append)

    response = TestClient(app).get("/health/ready")

    assert response.status_code == 200
    assert response.json() == {"status": "ok", "database": "ok"}
    assert checked == [app.state.engine]


def test_ready_hides_database_failure_details(make_app, monkeypatch) -> None:
    def fail_database_check(engine: object) -> None:
        raise SQLAlchemyError("sensitive connection details")

    monkeypatch.setattr(health, "check_database", fail_database_check)

    response = TestClient(make_app()).get("/health/ready")

    assert response.status_code == 503
    assert response.json() == {"status": "unavailable", "database": "unavailable"}
    assert "sensitive connection details" not in response.text


def test_ready_reports_unreachable_database(make_app) -> None:
    # The default test settings point at a port that refuses connections.
    response = TestClient(make_app()).get("/health/ready")

    assert response.status_code == 503
    assert response.json() == {"status": "unavailable", "database": "unavailable"}
