"""Accounts and sessions (P2-01, P2-14) against the PostgreSQL test database."""

import uuid
from collections.abc import Callable
from pathlib import Path

import pytest
from argon2 import PasswordHasher
from fastapi import FastAPI
from fastapi.testclient import TestClient
from sqlalchemy import text

from app.core.security import PasswordHashing, hash_session_token
from app.main import create_app
from tests.support import (
    CSRF_HEADERS,
    DEFAULT_PASSWORD,
    error_code,
    login,
    make_settings,
    register,
)

pytestmark = pytest.mark.integration

ClientFactory = Callable[[FastAPI], TestClient]
SESSION_COOKIE = "eka_session"


def _cookie_attributes(set_cookie: str) -> list[str]:
    return [part.strip().lower() for part in set_cookie.split(";")]


def _me_with_token(app: FastAPI, make_client: ClientFactory, token: str) -> int:
    response = make_client(app).get(
        "/api/v1/auth/me", headers={"Cookie": f"{SESSION_COOKIE}={token}"}
    )
    return response.status_code


def test_register_signs_in_with_a_protected_cookie(db_app, make_client) -> None:
    client = make_client(db_app)

    response = register(client, email="  Reader@Example.COM ")

    assert response.status_code == 201
    user = response.json()
    assert user["email"] == "reader@example.com"
    uuid.UUID(user["id"])
    attributes = _cookie_attributes(response.headers["set-cookie"])
    assert attributes[0].startswith(f"{SESSION_COOKIE}=")
    assert {"httponly", "samesite=strict", "path=/", "max-age=43200"} <= set(attributes)
    assert "secure" not in attributes
    me = client.get("/api/v1/auth/me")
    assert me.status_code == 200
    assert me.json() == user


def test_cookie_is_marked_secure_when_configured(make_db_app, make_client) -> None:
    response = register(make_client(make_db_app(session_cookie_secure=True)))

    assert response.status_code == 201
    assert "secure" in _cookie_attributes(response.headers["set-cookie"])


def test_an_email_can_be_registered_only_once(db_app, make_client) -> None:
    assert register(make_client(db_app)).status_code == 201

    response = register(make_client(db_app), email="READER@example.com")

    assert response.status_code == 409
    assert error_code(response) == "email_already_registered"


def test_registration_needs_a_password_of_at_least_12_characters(db_app, make_client) -> None:
    response = register(make_client(db_app), password="x" * 11)

    assert response.status_code == 422
    assert error_code(response) == "validation_failed"
    assert [field["location"] for field in response.json()["error"]["fields"]] == ["body.password"]


def test_registration_can_be_turned_off(make_db_app, make_client) -> None:
    response = register(make_client(make_db_app(registration_enabled=False)))

    assert response.status_code == 403
    assert error_code(response) == "registration_disabled"


def test_sign_in_with_correct_credentials(db_app, make_client) -> None:
    register(make_client(db_app))
    client = make_client(db_app)

    response = login(client, email="READER@example.com")

    assert response.status_code == 200
    assert response.json()["email"] == "reader@example.com"
    assert client.get("/api/v1/auth/me").status_code == 200


def test_wrong_password_and_unknown_email_get_the_same_answer(db_app, make_client) -> None:
    register(make_client(db_app))

    wrong_password = login(make_client(db_app), password="not the right password")
    unknown_email = login(make_client(db_app), email="nobody@example.com")

    for response in (wrong_password, unknown_email):
        assert response.status_code == 401
        assert error_code(response) == "invalid_credentials"
        assert "set-cookie" not in response.headers
    assert wrong_password.json()["error"]["message"] == unknown_email.json()["error"]["message"]


def test_signing_in_again_replaces_the_browser_session(db_app, make_client) -> None:
    client = make_client(db_app)
    register(client)
    first_token = client.cookies[SESSION_COOKIE]

    assert login(client).status_code == 200

    second_token = client.cookies[SESSION_COOKIE]
    assert second_token != first_token
    assert _me_with_token(db_app, make_client, first_token) == 401
    assert _me_with_token(db_app, make_client, second_token) == 200


def test_sign_out_ends_the_session(db_app, make_client) -> None:
    client = make_client(db_app)
    register(client)
    token = client.cookies[SESSION_COOKIE]

    response = client.post("/api/v1/auth/logout", headers=CSRF_HEADERS)

    assert response.status_code == 204
    assert SESSION_COOKIE not in client.cookies
    assert client.get("/api/v1/auth/me").status_code == 401
    assert _me_with_token(db_app, make_client, token) == 401


def test_sign_out_without_a_session_still_succeeds(db_app, make_client) -> None:
    response = make_client(db_app).post("/api/v1/auth/logout", headers=CSRF_HEADERS)

    assert response.status_code == 204


def test_unknown_session_tokens_are_refused(db_app, make_client) -> None:
    status = _me_with_token(db_app, make_client, "made-up-token-of-a-plausible-length-1234567")

    assert status == 401


def test_expired_sessions_are_refused_and_cleaned_up(db_app, make_client) -> None:
    client = make_client(db_app)
    register(client)
    with db_app.state.engine.begin() as connection:
        connection.execute(
            text("UPDATE user_sessions SET expires_at = now() - interval '1 minute'")
        )

    response = client.get("/api/v1/auth/me")

    assert response.status_code == 401
    assert error_code(response) == "not_authenticated"
    assert login(make_client(db_app)).status_code == 200
    with db_app.state.engine.connect() as connection:
        remaining = connection.scalar(text("SELECT count(*) FROM user_sessions"))
    assert remaining == 1


def test_only_hashes_of_passwords_and_session_tokens_are_stored(db_app, make_client) -> None:
    client = make_client(db_app)
    register(client)
    token = client.cookies[SESSION_COOKIE]

    with db_app.state.engine.connect() as connection:
        password_hash = connection.scalar(text("SELECT password_hash FROM users"))
        token_hashes = connection.scalars(text("SELECT token_hash FROM user_sessions")).all()

    assert password_hash.startswith("$argon2id$")
    assert DEFAULT_PASSWORD not in password_hash
    assert token_hashes == [hash_session_token(token)]


def test_sign_in_upgrades_outdated_password_hashes(
    db_app, make_client, database_url: str, storage_dir: Path
) -> None:
    register(make_client(db_app))
    stronger = PasswordHashing(PasswordHasher(time_cost=2, memory_cost=16, parallelism=1))
    app = create_app(
        make_settings(database_url=database_url, storage_dir=storage_dir), passwords=stronger
    )
    try:
        assert login(make_client(app)).status_code == 200
        with app.state.engine.connect() as connection:
            password_hash = connection.scalar(text("SELECT password_hash FROM users"))
    finally:
        app.state.engine.dispose()

    assert "$m=16,t=2,p=1$" in password_hash
    assert stronger.verify(password_hash, DEFAULT_PASSWORD)
