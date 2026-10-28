"""Workspaces (P2-04) against the PostgreSQL test database."""

import pytest

from tests.support import CSRF_HEADERS, create_workspace, error_code, register

pytestmark = pytest.mark.integration


@pytest.fixture
def client(db_app, make_client):
    client = make_client(db_app)
    assert register(client).status_code == 201
    return client


def test_create_and_list_workspaces(client) -> None:
    first = create_workspace(client, "  Research \t notes ")
    second = create_workspace(client, "Policies")

    response = client.get("/api/v1/workspaces")

    assert first["name"] == "Research notes"
    assert first["role"] == "owner"
    assert response.status_code == 200
    assert response.json()["items"] == [first, second]


def test_new_accounts_start_with_no_workspaces(client) -> None:
    assert client.get("/api/v1/workspaces").json() == {"items": []}


def test_a_name_of_100_characters_is_accepted(client) -> None:
    assert create_workspace(client, "n" * 100)["name"] == "n" * 100


@pytest.mark.parametrize(
    "name",
    ["", "   ", "n" * 101, "n" * 1001, "zero\u200bwidth", "null\x00byte"],
)
def test_invalid_workspace_names_are_rejected(client, name: str) -> None:
    response = client.post("/api/v1/workspaces", json={"name": name}, headers=CSRF_HEADERS)

    assert response.status_code == 422
    assert error_code(response) == "validation_failed"
    assert client.get("/api/v1/workspaces").json() == {"items": []}


def test_signed_out_users_cannot_use_workspaces(db_app, make_client) -> None:
    anonymous = make_client(db_app)

    listed = anonymous.get("/api/v1/workspaces")
    created = anonymous.post("/api/v1/workspaces", json={"name": "x"}, headers=CSRF_HEADERS)

    assert (listed.status_code, created.status_code) == (401, 401)
    assert error_code(created) == "not_authenticated"
