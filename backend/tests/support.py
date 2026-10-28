"""Helpers shared by the tests: settings, sample files, and API calls."""

import io
import zipfile
from pathlib import Path
from typing import Any

from fastapi.testclient import TestClient
from httpx2 import Response

from app.core.config import Settings

CSRF_HEADERS = {"X-CSRF-Protection": "1"}
# Port 9 (discard) refuses connections, so unit tests fail fast if they touch the database.
UNREACHABLE_DATABASE_URL = "postgresql+psycopg://nobody:nothing@127.0.0.1:9/unit_tests"
DEFAULT_PASSWORD = "correct horse battery staple"
TXT_MIME = "text/plain"
PDF_MIME = "application/pdf"
DOCX_MIME = "application/vnd.openxmlformats-officedocument.wordprocessingml.document"


def make_settings(**overrides: Any) -> Settings:
    values: dict[str, Any] = {
        "database_url": UNREACHABLE_DATABASE_URL,
        "database_connect_timeout_seconds": 1,
    }
    values.update(overrides)
    return Settings(_env_file=None, **values)


def pdf_bytes(text: str = "Synthetic test PDF") -> bytes:
    # Enough for the signature check; real parsing arrives in Phase 3.
    return f"%PDF-1.4\n% {text}\n1 0 obj\n<< >>\nendobj\ntrailer\n<< >>\n%%EOF\n".encode()


def docx_bytes(text: str = "Synthetic test document") -> bytes:
    buffer = io.BytesIO()
    with zipfile.ZipFile(buffer, "w") as archive:
        archive.writestr("[Content_Types].xml", "<Types/>")
        archive.writestr("word/document.xml", f"<document><body>{text}</body></document>")
    return buffer.getvalue()


def zip_bytes(entries: dict[str, str]) -> bytes:
    buffer = io.BytesIO()
    with zipfile.ZipFile(buffer, "w") as archive:
        for name, content in entries.items():
            archive.writestr(name, content)
    return buffer.getvalue()


def register(
    client: TestClient, email: str = "reader@example.com", password: str = DEFAULT_PASSWORD
) -> Response:
    return client.post(
        "/api/v1/auth/register",
        json={"email": email, "password": password},
        headers=CSRF_HEADERS,
    )


def login(
    client: TestClient, email: str = "reader@example.com", password: str = DEFAULT_PASSWORD
) -> Response:
    return client.post(
        "/api/v1/auth/login",
        json={"email": email, "password": password},
        headers=CSRF_HEADERS,
    )


def create_workspace(client: TestClient, name: str = "Research notes") -> dict[str, Any]:
    response = client.post("/api/v1/workspaces", json={"name": name}, headers=CSRF_HEADERS)
    assert response.status_code == 201, response.text
    workspace: dict[str, Any] = response.json()
    return workspace


def upload(
    client: TestClient,
    workspace_id: str,
    filename: str,
    content: bytes,
    mime_type: str = "application/octet-stream",
) -> Response:
    return client.post(
        f"/api/v1/workspaces/{workspace_id}/documents",
        files={"file": (filename, content, mime_type)},
        headers=CSRF_HEADERS,
    )


def error_code(response: Response) -> str:
    code: str = response.json()["error"]["code"]
    return code


def stored_files(storage_dir: Path) -> list[Path]:
    """Every file under the storage folder, including leftover temporary uploads."""
    return sorted(path for path in storage_dir.rglob("*") if path.is_file())
