"""The error contract, request IDs, CORS, and the CSRF header check. No database needed."""

from fastapi.testclient import TestClient

from app.core.errors import INTERNAL_ERROR_MESSAGE
from tests.support import CSRF_HEADERS, error_code

WEB_ORIGIN = "http://localhost:5173"


def _assert_error_shape(response, code: str) -> None:
    body = response.json()
    assert set(body) == {"error"}
    assert body["error"]["code"] == code
    assert body["error"]["message"]
    assert body["error"]["request_id"] == response.headers["X-Request-ID"]


def test_unknown_path_returns_standard_error(make_app) -> None:
    response = TestClient(make_app()).get("/api/v1/nothing-here")

    assert response.status_code == 404
    _assert_error_shape(response, "not_found")


def test_wrong_method_returns_standard_error_with_allow_header(make_app) -> None:
    response = TestClient(make_app()).put("/health/live")

    assert response.status_code == 405
    _assert_error_shape(response, "method_not_allowed")
    assert "GET" in response.headers["Allow"]


def test_every_response_gets_a_new_request_id(make_app) -> None:
    client = TestClient(make_app())

    first = client.get("/health/live", headers={"X-Request-ID": "client-chosen"})
    second = client.get("/health/live")

    assert len(first.headers["X-Request-ID"]) == 32
    assert first.headers["X-Request-ID"] != "client-chosen"
    assert first.headers["X-Request-ID"] != second.headers["X-Request-ID"]


def test_validation_errors_list_fields_without_echoing_input(make_app) -> None:
    secret_password = "too-short"
    response = TestClient(make_app()).post(
        "/api/v1/auth/register",
        json={"email": "not-an-email", "password": secret_password},
        headers=CSRF_HEADERS,
    )

    assert response.status_code == 422
    _assert_error_shape(response, "validation_failed")
    fields = {field["location"]: field["message"] for field in response.json()["error"]["fields"]}
    assert fields["body.email"] == "Enter a valid email address."
    assert "body.password" in fields
    assert secret_password not in response.text
    assert "not-an-email" not in response.text


def test_malformed_json_is_a_validation_error(make_app) -> None:
    response = TestClient(make_app()).post(
        "/api/v1/auth/login",
        content=b"{not json",
        headers={**CSRF_HEADERS, "Content-Type": "application/json"},
    )

    assert response.status_code == 422
    assert error_code(response) == "validation_failed"


def test_state_changing_requests_need_the_csrf_header(make_app) -> None:
    client = TestClient(make_app())

    response = client.post("/api/v1/auth/logout")
    wrong_value = client.post("/api/v1/auth/logout", headers={"X-CSRF-Protection": "yes"})

    assert response.status_code == 403
    _assert_error_shape(response, "csrf_header_missing")
    assert wrong_value.status_code == 403


def test_unhandled_errors_return_safe_json_that_browsers_can_read(make_app, caplog) -> None:
    app = make_app()

    def explode() -> None:
        raise RuntimeError("secret internal detail")

    app.add_api_route("/explode", explode)
    client = TestClient(app, raise_server_exceptions=False)

    response = client.get("/explode", headers={"Origin": WEB_ORIGIN})

    assert response.status_code == 500
    _assert_error_shape(response, "internal_error")
    assert response.json()["error"]["message"] == INTERNAL_ERROR_MESSAGE
    assert "secret internal detail" not in response.text
    assert response.headers["Access-Control-Allow-Origin"] == WEB_ORIGIN
    assert response.headers["X-Request-ID"] in caplog.text


def test_cors_preflight_allows_the_web_app_with_credentials(make_app) -> None:
    response = TestClient(make_app()).options(
        "/api/v1/workspaces",
        headers={
            "Origin": WEB_ORIGIN,
            "Access-Control-Request-Method": "POST",
            "Access-Control-Request-Headers": "content-type,x-csrf-protection",
        },
    )

    assert response.status_code == 200
    assert response.headers["Access-Control-Allow-Origin"] == WEB_ORIGIN
    assert response.headers["Access-Control-Allow-Credentials"] == "true"
    allowed_methods = response.headers["Access-Control-Allow-Methods"]
    assert "DELETE" in allowed_methods
    assert "PUT" not in allowed_methods


def test_cors_preflight_rejects_other_origins(make_app) -> None:
    response = TestClient(make_app()).options(
        "/api/v1/workspaces",
        headers={
            "Origin": "https://attacker.example",
            "Access-Control-Request-Method": "POST",
            "Access-Control-Request-Headers": "x-csrf-protection",
        },
    )

    assert response.status_code == 400
    assert "Access-Control-Allow-Origin" not in response.headers


def test_signed_out_requests_get_401(make_app) -> None:
    response = TestClient(make_app()).get(
        "/api/v1/auth/me", headers={"Cookie": "eka_session=" + "x" * 500}
    )

    assert response.status_code == 401
    _assert_error_shape(response, "not_authenticated")
