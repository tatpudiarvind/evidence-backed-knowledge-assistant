from fastapi.testclient import TestClient
from sqlalchemy.exc import SQLAlchemyError

from app.api import health
from app.main import app

client = TestClient(app)


def test_live_reports_process_is_running() -> None:
    response = client.get("/health/live")

    assert response.status_code == 200
    assert response.json() == {"status": "ok"}


def test_ready_reports_database_available(monkeypatch) -> None:
    monkeypatch.setattr(health, "check_database", lambda: None)

    response = client.get("/health/ready")

    assert response.status_code == 200
    assert response.json() == {"status": "ok", "database": "ok"}


def test_ready_hides_database_failure_details(monkeypatch) -> None:
    def fail_database_check() -> None:
        raise SQLAlchemyError("sensitive connection details")

    monkeypatch.setattr(health, "check_database", fail_database_check)

    response = client.get("/health/ready")

    assert response.status_code == 503
    assert response.json() == {"status": "unavailable", "database": "unavailable"}
    assert "sensitive connection details" not in response.text
