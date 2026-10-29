"""Rate limits on signing in, registering, and asking questions (P5-04).

The limiter is tested with a fake clock. The API tests turn the limits on, which the other
tests leave off, and give the app the same fake clock, so nothing waits.
"""

from collections.abc import Callable
from typing import Any

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from app.core.rate_limits import RateLimit, RateLimits, SlidingWindowLimiter, format_wait
from tests.conftest import AppFactory
from tests.support import ask, create_workspace, error_code, login, register

ClientFactory = Callable[[FastAPI], TestClient]


class FakeClock:
    def __init__(self) -> None:
        self.now = 1000.0

    def __call__(self) -> float:
        return self.now

    def advance(self, seconds: float) -> None:
        self.now += seconds


def _limiter(max_requests: int, clock: FakeClock, **options: Any) -> SlidingWindowLimiter:
    return SlidingWindowLimiter(RateLimit(max_requests, 60), clock=clock, **options)


def test_allows_the_limit_then_says_how_long_to_wait() -> None:
    clock = FakeClock()
    limiter = _limiter(3, clock)

    allowed = [limiter.acquire("a") for _ in range(3)]
    clock.advance(10.5)

    assert allowed == [None, None, None]
    assert limiter.acquire("a") == 50


def test_allows_again_once_the_oldest_request_leaves_the_window() -> None:
    clock = FakeClock()
    limiter = _limiter(2, clock)
    limiter.acquire("a")
    clock.advance(30)
    limiter.acquire("a")

    clock.advance(29.5)
    assert limiter.acquire("a") == 1
    clock.advance(0.5)
    assert limiter.acquire("a") is None
    assert limiter.acquire("a") == 30


def test_refused_requests_are_not_counted() -> None:
    clock = FakeClock()
    limiter = _limiter(1, clock)
    limiter.acquire("a")

    waits = []
    for _ in range(5):
        clock.advance(10)
        waits.append(limiter.acquire("a"))
    clock.advance(10)

    assert waits == [50, 40, 30, 20, 10]
    assert limiter.acquire("a") is None


def test_each_key_has_its_own_count() -> None:
    clock = FakeClock()
    limiter = _limiter(1, clock)

    assert limiter.acquire("a") is None
    assert limiter.acquire("b") is None
    assert limiter.acquire("a") == 60
    assert limiter.acquire("b") == 60


def test_forgets_the_least_recently_seen_key_beyond_the_maximum() -> None:
    clock = FakeClock()
    limiter = _limiter(1, clock, max_keys=2)
    limiter.acquire("a")
    limiter.acquire("b")
    # Refused, but it makes "a" more recent than "b".
    limiter.acquire("a")
    limiter.acquire("c")

    assert limiter.acquire("a") == 60
    assert limiter.acquire("c") == 60
    assert limiter.acquire("b") is None


@pytest.mark.parametrize(
    ("seconds", "expected"),
    [
        (1, "1 second"),
        (45, "45 seconds"),
        (59, "59 seconds"),
        (60, "1 minute"),
        (61, "2 minutes"),
        (3600, "60 minutes"),
    ],
)
def test_waits_are_given_in_seconds_or_whole_minutes(seconds: int, expected: str) -> None:
    assert format_wait(seconds) == expected


def _limited_app(make_db_app: AppFactory, clock: FakeClock, **settings: Any) -> FastAPI:
    app = make_db_app(rate_limits_enabled=True, **settings)
    app.state.rate_limits = RateLimits(app.state.settings, clock=clock)
    return app


def _assert_rate_limited(response, retry_after: int, message: str) -> None:
    assert response.status_code == 429
    assert error_code(response) == "rate_limited"
    assert response.headers["Retry-After"] == str(retry_after)
    error = response.json()["error"]
    assert error["message"] == message
    assert error["request_id"] == response.headers["X-Request-ID"]


@pytest.mark.integration
def test_sign_in_attempts_are_limited_per_address(make_db_app, make_client) -> None:
    clock = FakeClock()
    app = _limited_app(make_db_app, clock, sign_in_attempts_per_minute=2)
    client = make_client(app)
    assert register(client).status_code == 201

    wrong_passwords = [login(client, password="a wrong password").status_code for _ in range(2)]
    right_password = login(client)
    other_address = TestClient(app, raise_server_exceptions=False, client=("192.0.2.7", 50000))

    assert wrong_passwords == [401, 401]
    _assert_rate_limited(right_password, 60, "Too many sign-in attempts. Try again in 1 minute.")
    assert login(other_address).status_code == 200
    clock.advance(60)
    assert login(client).status_code == 200


@pytest.mark.integration
def test_registration_attempts_are_limited_per_address(make_db_app, make_client) -> None:
    clock = FakeClock()
    app = _limited_app(make_db_app, clock, registration_attempts_per_hour=1)

    first = register(make_client(app), email="first@example.com")
    second = register(make_client(app), email="second@example.com")

    assert first.status_code == 201
    _assert_rate_limited(second, 3600, "Too many registration attempts. Try again in 60 minutes.")
    clock.advance(3600)
    assert register(make_client(app), email="second@example.com").status_code == 201


@pytest.mark.integration
def test_questions_are_limited_per_account(make_db_app, make_client) -> None:
    clock = FakeClock()
    app = _limited_app(make_db_app, clock, questions_per_minute=1)
    first_reader, second_reader = make_client(app), make_client(app)
    register(first_reader, email="first@example.com")
    register(second_reader, email="second@example.com")
    first_workspace = create_workspace(first_reader)["id"]
    second_workspace = create_workspace(second_reader)["id"]

    signed_out = ask(make_client(app), first_workspace, "When do meetings start?")
    allowed = ask(first_reader, first_workspace, "When do meetings start?")
    refused = ask(first_reader, first_workspace, "Where are the records kept?")
    other_account = ask(second_reader, second_workspace, "When do meetings start?")

    # Signed-out requests are turned away before they're counted.
    assert signed_out.status_code == 401
    assert allowed.status_code == 201
    _assert_rate_limited(
        refused, 60, "You've asked too many questions in the last minute. Try again in 1 minute."
    )
    assert other_account.status_code == 201
    clock.advance(60)
    assert ask(first_reader, first_workspace, "Where are the records kept?").status_code == 201


@pytest.mark.integration
def test_the_limits_can_be_turned_off(make_db_app, make_client) -> None:
    client = make_client(make_db_app(rate_limits_enabled=False, sign_in_attempts_per_minute=1))
    register(client)

    assert [login(client).status_code for _ in range(3)] == [200, 200, 200]
