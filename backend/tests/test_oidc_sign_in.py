"""Signing in through an OpenID Connect provider (Phase 10, D-85).

The provider is a small server on this computer's loopback address that serves a discovery
document, a key set and a token endpoint, and signs ID tokens with a key made for the test. The
real code runs against it end to end, apart from the browser.
"""

import json
import threading
import time
import uuid
from collections.abc import Callable, Iterator
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from typing import Any
from urllib.parse import parse_qs, urlsplit

import jwt
import pytest
from cryptography.hazmat.primitives.asymmetric import rsa
from fastapi import FastAPI
from fastapi.testclient import TestClient
from sqlalchemy import text

from tests.support import login, register

pytestmark = pytest.mark.integration

CLIENT_ID = "knowledge-assistant"
REDIRECT_URI = "http://localhost:5173/api/v1/auth/oidc/callback"
LOGIN_URL = "/api/v1/auth/oidc/login"
CALLBACK_URL = "/api/v1/auth/oidc/callback"
LOGIN_COOKIE = "eka_oidc_login"
SESSION_COOKIE = "eka_session"
ClientFactory = Callable[[FastAPI], TestClient]


class FakeProvider:
    def __init__(self) -> None:
        self.private_key = rsa.generate_private_key(public_exponent=65537, key_size=2048)
        self.other_key = rsa.generate_private_key(public_exponent=65537, key_size=2048)
        self.key_id = "key-1"
        self.published_key_ids = ["key-1"]
        self.tokens: dict[str, str] = {}
        self.token_requests: list[dict[str, Any]] = []
        self.key_fetches = 0
        self._server = ThreadingHTTPServer(("127.0.0.1", 0), self._handler())
        self.issuer = f"http://127.0.0.1:{self._server.server_address[1]}"
        self.discovery_issuer = self.issuer
        threading.Thread(target=self._server.serve_forever, daemon=True).start()

    def stop(self) -> None:
        self._server.shutdown()
        self._server.server_close()

    def _jwk(self, key_id: str) -> dict[str, Any]:
        document = json.loads(jwt.algorithms.RSAAlgorithm.to_jwk(self.private_key.public_key()))
        return {**document, "kid": key_id, "use": "sig", "alg": "RS256"}

    def _handler(self) -> type[BaseHTTPRequestHandler]:
        provider = self

        class Handler(BaseHTTPRequestHandler):
            def log_message(self, *args: object) -> None:
                pass

            def _send(self, status: int, body: dict[str, Any]) -> None:
                payload = json.dumps(body).encode()
                self.send_response(status)
                self.send_header("Content-Type", "application/json")
                self.send_header("Content-Length", str(len(payload)))
                self.end_headers()
                self.wfile.write(payload)

            def do_GET(self) -> None:
                if self.path == "/.well-known/openid-configuration":
                    self._send(
                        200,
                        {
                            "issuer": provider.discovery_issuer,
                            "authorization_endpoint": provider.issuer + "/authorize",
                            "token_endpoint": provider.issuer + "/token",
                            "jwks_uri": provider.issuer + "/keys",
                        },
                    )
                elif self.path == "/keys":
                    provider.key_fetches += 1
                    self._send(
                        200, {"keys": [provider._jwk(kid) for kid in provider.published_key_ids]}
                    )
                else:
                    self._send(404, {})

            def do_POST(self) -> None:
                length = int(self.headers.get("Content-Length", "0"))
                form = parse_qs(self.rfile.read(length).decode())
                request = {key: values[0] for key, values in form.items()}
                request["authorization"] = self.headers.get("Authorization", "")
                provider.token_requests.append(request)
                token = provider.tokens.pop(request.get("code", ""), None)
                if token is None:
                    self._send(400, {"error": "invalid_grant"})
                else:
                    self._send(200, {"id_token": token, "access_token": "unused"})

        return Handler

    def issue(self, expected_nonce: str, /, **changes: Any) -> str:
        """Makes a token for a nonce and returns the code that exchanges for it."""
        now = int(time.time())
        claims: dict[str, Any] = {
            "iss": self.issuer,
            "aud": CLIENT_ID,
            "sub": "subject-1",
            "iat": now,
            "exp": now + 300,
            "nonce": expected_nonce,
            "email": "person@example.com",
            "email_verified": True,
        }
        claims.update(changes)
        claims = {key: value for key, value in claims.items() if value is not None}
        token = jwt.encode(
            claims,
            self.private_key,
            algorithm="RS256",
            headers={"kid": self.key_id},
        )
        code = uuid.uuid4().hex
        self.tokens[code] = token
        return code


@pytest.fixture
def provider() -> Iterator[FakeProvider]:
    fake = FakeProvider()
    yield fake
    fake.stop()


@pytest.fixture
def make_oidc_app(make_db_app, provider: FakeProvider) -> Callable[..., FastAPI]:
    def factory(**overrides: Any) -> FastAPI:
        settings: dict[str, Any] = {
            "auth_mode": "oidc",
            "oidc_issuer": provider.issuer,
            "oidc_client_id": CLIENT_ID,
            "oidc_client_secret": "a-secret",
            "oidc_redirect_uri": REDIRECT_URI,
            "oidc_provider_name": "Example ID",
            "session_cookie_secure": False,
        }
        settings.update(overrides)
        return make_db_app(**settings)

    return factory


def _start(client: TestClient, return_to: str | None = None) -> tuple[dict[str, list[str]], Any]:
    params = {"return_to": return_to} if return_to is not None else None
    response = client.get(LOGIN_URL, params=params, follow_redirects=False)
    assert response.status_code == 302, response.text
    return parse_qs(urlsplit(response.headers["location"]).query), response


def _finish(
    client: TestClient, provider: FakeProvider, query: dict[str, list[str]], **changes: Any
) -> Any:
    code = provider.issue(query["nonce"][0], **changes)
    return client.get(
        CALLBACK_URL, params={"code": code, "state": query["state"][0]}, follow_redirects=False
    )


def _refused(response: Any, code: str) -> None:
    assert response.status_code == 303
    assert response.headers["location"] == f"/?sign_in_error={code}"
    assert SESSION_COOKIE not in response.cookies


def _sign_in(client: TestClient, provider: FakeProvider, **changes: Any) -> Any:
    query, _ = _start(client)
    return _finish(client, provider, query, **changes)


def test_sign_in_creates_an_account_and_a_session(make_oidc_app, make_client, provider) -> None:
    client = make_client(make_oidc_app())

    query, started = _start(client, "/workspaces")
    assert query["code_challenge_method"] == ["S256"]
    assert query["client_id"] == [CLIENT_ID]
    assert query["redirect_uri"] == [REDIRECT_URI]
    assert "openid" in query["scope"][0].split()
    attributes = started.headers["set-cookie"].lower()
    assert "httponly" in attributes and "samesite=lax" in attributes
    assert "path=/api/v1/auth/oidc" in attributes

    response = _finish(client, provider, query)

    assert response.status_code == 303
    assert response.headers["location"] == "/workspaces"
    assert "samesite=strict" in response.headers["set-cookie"].lower()
    me = client.get("/api/v1/auth/me")
    assert me.status_code == 200
    assert me.json()["email"] == "person@example.com"
    request = provider.token_requests[0]
    assert request["grant_type"] == "authorization_code"
    assert request["redirect_uri"] == REDIRECT_URI
    assert request["authorization"].startswith("Basic ")
    assert len(request["code_verifier"]) >= 43
    assert "a-secret" not in json.dumps({k: v for k, v in request.items() if k != "authorization"})


def test_a_second_sign_in_finds_the_same_account(make_oidc_app, make_client, provider) -> None:
    app = make_oidc_app()
    first = make_client(app)
    _sign_in(first, provider)
    user_id = first.get("/api/v1/auth/me").json()["id"]

    second = make_client(app)
    # A changed email address doesn't make a different person: the subject decides.
    _sign_in(second, provider, email="renamed@example.com")

    assert second.get("/api/v1/auth/me").json()["id"] == user_id
    with app.state.engine.connect() as connection:
        count = connection.execute(text("select count(*) from user_identities")).scalar()
    assert count == 1


def test_the_login_state_is_single_use(make_oidc_app, make_client, provider) -> None:
    client = make_client(make_oidc_app())
    query, _ = _start(client)
    assert _finish(client, provider, query).headers["location"] == "/"

    # The same cookie and state again: the state was taken the first time.
    client.cookies.set(LOGIN_COOKIE, "x", path="/api/v1/auth/oidc")
    _refused(_finish(client, provider, query), "sign_in_expired")


def test_a_wrong_state_is_refused(make_oidc_app, make_client, provider) -> None:
    client = make_client(make_oidc_app())
    query, _ = _start(client)
    code = provider.issue(query["nonce"][0])

    response = client.get(
        CALLBACK_URL, params={"code": code, "state": "not-the-state"}, follow_redirects=False
    )

    _refused(response, "sign_in_refused")
    assert provider.token_requests == []


def test_a_callback_without_the_login_cookie_is_refused(
    make_oidc_app, make_client, provider
) -> None:
    app = make_oidc_app()
    query, _ = _start(make_client(app))
    other_browser = make_client(app)

    _refused(_finish(other_browser, provider, query), "sign_in_expired")
    assert provider.token_requests == []


def test_an_expired_login_is_refused(make_oidc_app, make_client, provider) -> None:
    app = make_oidc_app()
    client = make_client(app)
    query, _ = _start(client)
    with app.state.engine.begin() as connection:
        connection.execute(
            text("update oidc_login_states set expires_at = now() - interval '1 minute'")
        )

    _refused(_finish(client, provider, query), "sign_in_expired")


def test_the_provider_reporting_an_error_is_refused(make_oidc_app, make_client) -> None:
    client = make_client(make_oidc_app())
    _start(client)

    response = client.get(CALLBACK_URL, params={"error": "access_denied"}, follow_redirects=False)

    _refused(response, "sign_in_refused")


@pytest.mark.parametrize(
    "changes",
    [
        {"aud": "another-client"},
        {"iss": "http://127.0.0.1:1"},
        {"exp": int(time.time()) - 3600},
        {"nonce": "another-nonce"},
        {"nonce": None},
        {"sub": None},
        {"sub": "s" * 256},
        {"aud": [CLIENT_ID, "other"]},
        {"azp": "another-client"},
    ],
    ids=[
        "audience",
        "issuer",
        "expired",
        "nonce",
        "no-nonce",
        "no-subject",
        "long-subject",
        "two-audiences-no-azp",
        "azp",
    ],
)
def test_a_bad_id_token_is_refused(make_oidc_app, make_client, provider, changes) -> None:
    client = make_client(make_oidc_app())

    _refused(_sign_in(client, provider, **changes), "sign_in_refused")
    assert client.get("/api/v1/auth/me").status_code == 401


def test_a_token_signed_with_another_key_is_refused(make_oidc_app, make_client, provider) -> None:
    client = make_client(make_oidc_app())
    query, _ = _start(client)
    now = int(time.time())
    token = jwt.encode(
        {
            "iss": provider.issuer,
            "aud": CLIENT_ID,
            "sub": "attacker",
            "iat": now,
            "exp": now + 300,
            "nonce": query["nonce"][0],
            "email": "person@example.com",
            "email_verified": True,
        },
        provider.other_key,
        algorithm="RS256",
        headers={"kid": provider.key_id},
    )
    provider.tokens["forged"] = token

    response = client.get(
        CALLBACK_URL, params={"code": "forged", "state": query["state"][0]}, follow_redirects=False
    )

    _refused(response, "sign_in_refused")


@pytest.mark.parametrize("algorithm", ["none", "HS256"])
def test_unsafe_algorithms_are_refused(make_oidc_app, make_client, provider, algorithm) -> None:
    client = make_client(make_oidc_app())
    query, _ = _start(client)
    now = int(time.time())
    claims = {
        "iss": provider.issuer,
        "aud": CLIENT_ID,
        "sub": "attacker",
        "iat": now,
        "exp": now + 300,
        "nonce": query["nonce"][0],
        "email": "person@example.com",
        "email_verified": True,
    }
    if algorithm == "none":
        token = jwt.encode(claims, None, algorithm="none", headers={"kid": provider.key_id})
    else:
        # The shared secret is the one the provider gave this client.
        token = jwt.encode(claims, "a-secret" * 8, algorithm="HS256", headers={"kid": "key-1"})
    provider.tokens["forged"] = token

    response = client.get(
        CALLBACK_URL, params={"code": "forged", "state": query["state"][0]}, follow_redirects=False
    )

    _refused(response, "sign_in_refused")


def test_an_unknown_key_id_refetches_keys_only_now_and_then(
    make_oidc_app, make_client, provider
) -> None:
    app = make_oidc_app()
    provider.key_id = "unlisted"
    for _ in range(3):
        _refused(_sign_in(make_client(app), provider), "sign_in_refused")

    # The keys were fetched once; the unknown ids didn't make the API fetch them again.
    assert provider.key_fetches == 1


def test_a_rotated_key_is_picked_up(make_oidc_app, make_client, provider) -> None:
    app = make_oidc_app()
    assert _sign_in(make_client(app), provider).status_code == 303
    provider.key_id = "key-2"
    provider.published_key_ids = ["key-1", "key-2"]
    app.state.oidc._keys_at = time.monotonic() - 3600

    client = make_client(app)
    response = _sign_in(client, provider)

    assert response.headers["location"] == "/"
    assert client.get("/api/v1/auth/me").status_code == 200


def test_a_discovery_document_naming_another_issuer_is_refused(
    make_oidc_app, make_client, provider
) -> None:
    provider.discovery_issuer = "http://127.0.0.1:1"
    client = make_client(make_oidc_app())

    response = client.get(LOGIN_URL, follow_redirects=False)

    assert response.status_code == 503
    assert response.json()["error"]["code"] == "sign_in_unavailable"


def test_a_provider_that_is_down_is_a_clear_error(make_oidc_app, make_client, provider) -> None:
    client = make_client(make_oidc_app())
    provider.stop()

    response = client.get(LOGIN_URL, follow_redirects=False)

    assert response.status_code == 503


def test_an_unverified_email_is_refused(make_oidc_app, make_client, provider) -> None:
    client = make_client(make_oidc_app())

    _refused(_sign_in(client, provider, email_verified=False), "email_not_verified")
    _refused(_sign_in(client, provider, email_verified="true"), "email_not_verified")
    _refused(_sign_in(client, provider, email=None), "email_not_verified")


def test_an_email_in_use_by_a_password_account_is_refused(
    make_oidc_app, make_client, provider
) -> None:
    app = make_oidc_app(auth_mode="both")
    assert register(make_client(app), email="person@example.com").status_code == 201
    client = make_client(app)

    _refused(_sign_in(client, provider), "email_in_use")


@pytest.mark.parametrize(
    "return_to",
    ["//evil.example", "https://evil.example", "/a\\b", "evil", "/" + "a" * 600, "/a\nb"],
)
def test_a_return_path_off_this_site_is_refused(make_oidc_app, make_client, return_to) -> None:
    client = make_client(make_oidc_app())

    response = client.get(LOGIN_URL, params={"return_to": return_to}, follow_redirects=False)

    assert response.status_code == 400
    assert response.json()["error"]["code"] == "invalid_return_path"


def test_the_options_follow_the_mode(make_oidc_app, make_client) -> None:
    oidc_only = make_client(make_oidc_app()).get("/api/v1/auth/options").json()
    both = make_client(make_oidc_app(auth_mode="both")).get("/api/v1/auth/options").json()

    assert oidc_only == {"password": False, "registration": False, "provider_name": "Example ID"}
    assert both == {"password": True, "registration": True, "provider_name": "Example ID"}


def test_password_routes_are_closed_in_oidc_mode(make_oidc_app, make_client) -> None:
    client = make_client(make_oidc_app())

    for response in (register(client), login(client)):
        assert response.status_code == 403
        assert response.json()["error"]["code"] == "password_sign_in_disabled"


def test_an_account_without_a_password_cannot_sign_in_with_one(
    make_oidc_app, make_client, provider
) -> None:
    app = make_oidc_app(auth_mode="both")
    _sign_in(make_client(app), provider)

    response = login(make_client(app), email="person@example.com", password="anything-at-all-1")

    assert response.status_code == 401
    assert response.json()["error"]["code"] == "invalid_credentials"


def test_the_provider_routes_are_missing_without_a_provider(db_app, make_client) -> None:
    client = make_client(db_app)

    assert client.get(LOGIN_URL, follow_redirects=False).status_code == 404
    options = client.get("/api/v1/auth/options").json()
    assert options == {"password": True, "registration": True, "provider_name": None}
