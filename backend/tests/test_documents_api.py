"""The document lifecycle (P2-06 - P2-08) against the PostgreSQL test database."""

import hashlib
import re
import uuid
from pathlib import Path
from typing import Any

import pytest
from fastapi.testclient import TestClient

from app.repositories import documents as document_repository
from tests.support import (
    CSRF_HEADERS,
    DOCX_MIME,
    PDF_MIME,
    create_workspace,
    docx_bytes,
    error_code,
    pdf_bytes,
    register,
    stored_files,
    upload,
)

pytestmark = pytest.mark.integration


@pytest.fixture
def owner(db_app, make_client) -> TestClient:
    client = make_client(db_app)
    assert register(client).status_code == 201
    return client


@pytest.fixture
def workspace_id(owner: TestClient) -> str:
    workspace_id: str = create_workspace(owner)["id"]
    return workspace_id


def _documents(client: TestClient, workspace_id: str) -> list[dict[str, Any]]:
    response = client.get(f"/api/v1/workspaces/{workspace_id}/documents")
    assert response.status_code == 200, response.text
    items: list[dict[str, Any]] = response.json()["items"]
    return items


@pytest.mark.parametrize(
    ("filename", "content", "mime_type"),
    [
        ("notes.txt", "Synthetic notes, caf\u00e9.\n".encode(), "text/plain"),
        ("paper.pdf", pdf_bytes(), PDF_MIME),
        ("report.docx", docx_bytes(), DOCX_MIME),
    ],
)
def test_upload_stores_the_file_and_queues_it(
    owner, workspace_id, storage_dir: Path, filename: str, content: bytes, mime_type: str
) -> None:
    # The browser's MIME type is ignored; the server decides from the checked file type.
    response = upload(owner, workspace_id, filename, content, "application/x-anything")

    assert response.status_code == 202
    document = response.json()
    assert document["workspace_id"] == workspace_id
    assert document["display_name"] == filename
    assert document["mime_type"] == mime_type
    assert document["size_bytes"] == len(content)
    assert document["sha256"] == hashlib.sha256(content).hexdigest()
    assert document["status"] == "queued"
    assert document["failure_code"] is None
    assert document["failure_message"] is None
    assert "storage_key" not in document
    [stored] = stored_files(storage_dir)
    assert stored.parent == storage_dir / "documents"
    assert re.fullmatch(r"[0-9a-f]{32}", stored.name)
    assert stored.read_bytes() == content


def test_documents_are_listed_newest_first(owner, workspace_id) -> None:
    first = upload(owner, workspace_id, "first.txt", b"one").json()
    second = upload(owner, workspace_id, "second.txt", b"two").json()

    assert _documents(owner, workspace_id) == [second, first]


def test_each_workspace_lists_only_its_own_documents(owner, workspace_id) -> None:
    other_workspace_id = create_workspace(owner, "Other")["id"]
    upload(owner, workspace_id, "first.txt", b"one")

    assert _documents(owner, other_workspace_id) == []


def test_document_details_match_the_upload(owner, workspace_id) -> None:
    uploaded = upload(owner, workspace_id, "notes.txt", b"text").json()

    response = owner.get(f"/api/v1/documents/{uploaded['id']}")

    assert response.status_code == 200
    assert response.json() == uploaded


def test_download_returns_the_original_file_as_an_attachment(owner, workspace_id) -> None:
    content = "Synthetic r\u00e9sum\u00e9 notes".encode()
    uploaded = upload(owner, workspace_id, "R\u00e9sum\u00e9 \u2013 notes.txt", content).json()

    response = owner.get(f"/api/v1/documents/{uploaded['id']}/file")

    assert response.status_code == 200
    assert response.content == content
    assert response.headers["content-type"].startswith("text/plain")
    assert response.headers["content-length"] == str(len(content))
    assert response.headers["cache-control"] == "no-store"
    assert response.headers["x-content-type-options"] == "nosniff"
    assert response.headers["content-disposition"] == (
        'attachment; filename="R_sum_ _ notes.txt"; '
        "filename*=UTF-8''R%C3%A9sum%C3%A9%20%E2%80%93%20notes.txt"
    )


def test_delete_removes_the_document_and_its_file(owner, workspace_id, storage_dir) -> None:
    uploaded = upload(owner, workspace_id, "notes.txt", b"text").json()

    response = owner.delete(f"/api/v1/documents/{uploaded['id']}", headers=CSRF_HEADERS)

    assert response.status_code == 204
    assert owner.get(f"/api/v1/documents/{uploaded['id']}").status_code == 404
    assert _documents(owner, workspace_id) == []
    assert stored_files(storage_dir) == []
    again = owner.delete(f"/api/v1/documents/{uploaded['id']}", headers=CSRF_HEADERS)
    assert error_code(again) == "document_not_found"


@pytest.mark.parametrize(
    ("filename", "content", "status", "code"),
    [
        ("program.exe", b"MZ\x90\x00", 415, "unsupported_file_type"),
        ("legacy.doc", b"\xd0\xcf\x11\xe0\xa1\xb1\x1a\xe1", 415, "unsupported_file_type"),
        ("no_extension", b"plain text", 415, "unsupported_file_type"),
        ("fake.pdf", b"plain text pretending to be a PDF", 422, "invalid_file_content"),
        ("fake.docx", pdf_bytes(), 422, "invalid_file_content"),
        ("latin1.txt", b"caf\xe9", 422, "invalid_file_content"),
        ("binary.txt", b"\x00\x01\x02\x03", 422, "invalid_file_content"),
        ("empty.txt", b"", 422, "file_empty"),
    ],
)
def test_invalid_uploads_are_rejected_and_nothing_is_kept(
    owner, workspace_id, storage_dir, filename: str, content: bytes, status: int, code: str
) -> None:
    response = upload(owner, workspace_id, filename, content)

    assert response.status_code == status
    assert error_code(response) == code
    assert stored_files(storage_dir) == []
    assert _documents(owner, workspace_id) == []


def test_files_over_the_size_limit_are_rejected(make_db_app, make_client, storage_dir) -> None:
    client = make_client(make_db_app(max_upload_bytes=1024))
    register(client)
    workspace_id = create_workspace(client)["id"]

    accepted = upload(client, workspace_id, "fits.txt", b"x" * 1024)
    rejected = upload(client, workspace_id, "big.txt", b"x" * 1025)

    assert accepted.status_code == 202
    assert rejected.status_code == 413
    assert error_code(rejected) == "file_too_large"
    assert len(stored_files(storage_dir)) == 1


def test_size_limit_message_names_the_limit_in_mebibytes(owner, workspace_id) -> None:
    response = upload(owner, workspace_id, "big.txt", b"x" * (10 * 1024 * 1024 + 1))

    assert response.status_code == 413
    assert response.json()["error"]["message"] == "Files can be at most 10 MiB."


def test_each_workspace_has_a_document_limit(make_db_app, make_client, storage_dir) -> None:
    client = make_client(make_db_app(max_documents_per_workspace=2))
    register(client)
    full_workspace_id = create_workspace(client)["id"]
    other_workspace_id = create_workspace(client, "Other")["id"]
    for name in ("one.txt", "two.txt"):
        assert upload(client, full_workspace_id, name, b"text").status_code == 202

    rejected = upload(client, full_workspace_id, "three.txt", b"text")

    assert rejected.status_code == 409
    assert error_code(rejected) == "document_limit_reached"
    assert len(stored_files(storage_dir)) == 2
    assert upload(client, other_workspace_id, "three.txt", b"text").status_code == 202


@pytest.mark.parametrize(
    ("filename", "display_name"),
    [
        ("../../etc/passwd.txt", "passwd.txt"),
        ("..\\..\\secret\\evil\u202egnp.txt", "evilgnp.txt"),
        ("  lots   of   space .txt", "lots of space.txt"),
    ],
)
def test_display_names_are_sanitized(owner, workspace_id, filename, display_name) -> None:
    response = upload(owner, workspace_id, filename, b"text")

    assert response.status_code == 202
    assert response.json()["display_name"] == display_name


def test_upload_to_an_unknown_workspace_is_refused(owner, storage_dir) -> None:
    response = upload(owner, str(uuid.uuid4()), "notes.txt", b"text")

    assert response.status_code == 404
    assert error_code(response) == "workspace_not_found"
    assert stored_files(storage_dir) == []


def test_malformed_ids_are_validation_errors(owner) -> None:
    response = owner.get("/api/v1/documents/not-a-uuid")

    assert response.status_code == 422
    assert error_code(response) == "validation_failed"


def test_failed_file_deletion_can_be_retried(
    db_app, owner, workspace_id, storage_dir, monkeypatch
) -> None:
    uploaded = upload(owner, workspace_id, "notes.txt", b"text").json()
    document_url = f"/api/v1/documents/{uploaded['id']}"

    def locked_file(key: str) -> None:
        raise PermissionError("the file is locked by another program")

    with monkeypatch.context() as patch:
        patch.setattr(db_app.state.storage, "delete", locked_file)
        failed = owner.delete(document_url, headers=CSRF_HEADERS)

    assert failed.status_code == 500
    assert error_code(failed) == "document_delete_failed"
    assert "locked" not in failed.text
    assert owner.get(document_url).json()["status"] == "deleting"
    download = owner.get(f"{document_url}/file")
    assert download.status_code == 409
    assert error_code(download) == "document_being_deleted"

    assert owner.delete(document_url, headers=CSRF_HEADERS).status_code == 204
    assert stored_files(storage_dir) == []
    assert _documents(owner, workspace_id) == []


def test_a_failed_database_write_leaves_no_file_behind(
    owner, workspace_id, storage_dir, monkeypatch
) -> None:
    def failing_add(*args: object) -> None:
        raise RuntimeError("simulated database failure")

    with monkeypatch.context() as patch:
        patch.setattr(document_repository, "add", failing_add)
        response = upload(owner, workspace_id, "notes.txt", b"text")

    assert response.status_code == 500
    assert error_code(response) == "internal_error"
    assert "simulated" not in response.text
    assert stored_files(storage_dir) == []
    assert _documents(owner, workspace_id) == []


def test_download_reports_a_missing_stored_file(owner, workspace_id, storage_dir) -> None:
    uploaded = upload(owner, workspace_id, "notes.txt", b"text").json()
    for path in stored_files(storage_dir):
        path.unlink()

    response = owner.get(f"/api/v1/documents/{uploaded['id']}/file")

    assert response.status_code == 404
    assert error_code(response) == "document_file_missing"
