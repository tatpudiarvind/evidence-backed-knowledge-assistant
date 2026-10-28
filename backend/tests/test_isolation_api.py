"""Phase 2's definition of done (P2-05, P2-12): one user can never reach another's documents.

Every denial looks the same as "not found", so IDs can't be probed for existence.
"""

from dataclasses import dataclass
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from tests.support import (
    CSRF_HEADERS,
    create_workspace,
    error_code,
    register,
    stored_files,
    upload,
)

pytestmark = pytest.mark.integration

PRIVATE_TEXT = b"Synthetic text that only its owner may read."


@dataclass
class TwoUsers:
    owner: TestClient
    intruder: TestClient
    anonymous: TestClient
    workspace_id: str
    document_id: str


@pytest.fixture
def users(db_app, make_client) -> TwoUsers:
    owner, intruder = make_client(db_app), make_client(db_app)
    assert register(owner, "owner@example.com").status_code == 201
    assert register(intruder, "intruder@example.com").status_code == 201
    workspace_id = create_workspace(owner, "Owner's notes")["id"]
    document = upload(owner, workspace_id, "private.txt", PRIVATE_TEXT)
    assert document.status_code == 202
    create_workspace(intruder, "Intruder's own workspace")
    return TwoUsers(owner, intruder, make_client(db_app), workspace_id, document.json()["id"])


def _owner_still_has_the_document(users: TwoUsers, storage_dir: Path) -> None:
    response = users.owner.get(f"/api/v1/workspaces/{users.workspace_id}/documents")
    assert [item["id"] for item in response.json()["items"]] == [users.document_id]
    assert [path.read_bytes() for path in stored_files(storage_dir)] == [PRIVATE_TEXT]


def test_other_workspaces_are_not_listed(users: TwoUsers) -> None:
    names = [item["name"] for item in users.intruder.get("/api/v1/workspaces").json()["items"]]

    assert names == ["Intruder's own workspace"]


def test_cannot_list_another_users_documents(users: TwoUsers) -> None:
    response = users.intruder.get(f"/api/v1/workspaces/{users.workspace_id}/documents")

    assert response.status_code == 404
    assert error_code(response) == "workspace_not_found"


def test_cannot_read_another_users_document_by_id(users: TwoUsers) -> None:
    response = users.intruder.get(f"/api/v1/documents/{users.document_id}")

    assert response.status_code == 404
    assert error_code(response) == "document_not_found"
    assert "private.txt" not in response.text


def test_cannot_download_another_users_document(users: TwoUsers) -> None:
    response = users.intruder.get(f"/api/v1/documents/{users.document_id}/file")

    assert response.status_code == 404
    assert error_code(response) == "document_not_found"
    assert PRIVATE_TEXT not in response.content


def test_cannot_delete_another_users_document(users: TwoUsers, storage_dir: Path) -> None:
    response = users.intruder.delete(f"/api/v1/documents/{users.document_id}", headers=CSRF_HEADERS)

    assert response.status_code == 404
    assert error_code(response) == "document_not_found"
    _owner_still_has_the_document(users, storage_dir)
    status = users.owner.get(f"/api/v1/documents/{users.document_id}").json()["status"]
    assert status == "queued"


def test_cannot_upload_into_another_users_workspace(users: TwoUsers, storage_dir: Path) -> None:
    response = upload(users.intruder, users.workspace_id, "planted.txt", b"Planted text")

    assert response.status_code == 404
    assert error_code(response) == "workspace_not_found"
    _owner_still_has_the_document(users, storage_dir)


@pytest.mark.parametrize(
    ("method", "path"),
    [
        ("GET", "/api/v1/auth/me"),
        ("GET", "/api/v1/workspaces"),
        ("GET", "/api/v1/workspaces/{workspace_id}/documents"),
        ("GET", "/api/v1/documents/{document_id}"),
        ("GET", "/api/v1/documents/{document_id}/file"),
        ("DELETE", "/api/v1/documents/{document_id}"),
    ],
)
def test_signed_out_requests_are_refused(users: TwoUsers, method: str, path: str) -> None:
    url = path.format(workspace_id=users.workspace_id, document_id=users.document_id)

    response = users.anonymous.request(method, url, headers=CSRF_HEADERS)

    assert response.status_code == 401
    assert error_code(response) == "not_authenticated"


def test_signed_out_uploads_are_refused(users: TwoUsers, storage_dir: Path) -> None:
    response = upload(users.anonymous, users.workspace_id, "planted.txt", b"Planted text")

    assert response.status_code == 401
    _owner_still_has_the_document(users, storage_dir)
