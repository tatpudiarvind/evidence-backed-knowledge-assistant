"""Metrics (Phase 5): the /metrics endpoint and what the API counts.

Only the last test needs the PostgreSQL test database; test_ingestion checks the indexing
counts.
"""

import uuid
from collections.abc import Callable

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from app.core.metrics import Metrics
from app.domain.questions import AbstentionReason, AnswerMode, AnswerRecord
from tests.conftest import AppFactory
from tests.support import (
    ask,
    create_workspace,
    error_code,
    metric_value,
    register,
    sample_value,
)

REQUESTS = "http_requests_total"
DURATIONS = "http_request_duration_seconds"
ANSWERS = "knowledge_assistant_answers_total"
PROCESSED = "knowledge_assistant_documents_processed_total"
OPENMETRICS = "application/openmetrics-text; version=1.0.0"
MALFORMED_OPENMETRICS = "application/openmetrics-text; version=x"


def test_metrics_are_not_served_unless_enabled(make_app: AppFactory) -> None:
    response = TestClient(make_app()).get("/metrics")

    assert response.status_code == 404
    assert error_code(response) == "not_found"


def test_requests_are_counted_by_method_route_and_status(make_app: AppFactory) -> None:
    client = TestClient(make_app(metrics_enabled=True))
    workspace_id = uuid.uuid4()

    client.get("/health/live")
    client.get("/health/live")
    client.get(f"/api/v1/workspaces/{workspace_id}/documents?q=synthetic-query")
    client.get("/synthetic-unknown-page")
    # Methods outside HTTP's usual ones are counted together.
    client.request("PROPFIND", "/health/live")
    exposition = client.get("/metrics").text

    def count(method: str, route: str, status: str) -> float | None:
        return sample_value(exposition, REQUESTS, method=method, route=route, status=status)

    assert count("GET", "/health/live", "200") == 2
    assert count("GET", "/api/v1/workspaces/{workspace_id}/documents", "401") == 1
    assert count("GET", "(no route)", "404") == 1
    assert count("OTHER", "/health/live", "405") == 1
    assert str(workspace_id) not in exposition
    assert "synthetic" not in exposition
    assert "PROPFIND" not in exposition


def test_request_durations_are_recorded_in_buckets(make_app: AppFactory) -> None:
    client = TestClient(make_app(metrics_enabled=True))

    client.get("/health/live")
    exposition = client.get("/metrics").text

    labels = {"method": "GET", "route": "/health/live"}
    assert sample_value(exposition, f"{DURATIONS}_count", **labels) == 1
    assert sample_value(exposition, f"{DURATIONS}_bucket", le="120.0", **labels) == 1
    assert sample_value(exposition, f"{DURATIONS}_bucket", le="+Inf", **labels) == 1


def test_metrics_come_in_prometheus_text_format_or_openmetrics_on_request(
    make_app: AppFactory,
) -> None:
    client = TestClient(make_app(metrics_enabled=True))
    client.get("/health/live")

    classic = client.get("/metrics")
    openmetrics = client.get("/metrics", headers={"Accept": OPENMETRICS})
    malformed = client.get("/metrics", headers={"Accept": MALFORMED_OPENMETRICS})

    assert classic.status_code == 200
    assert classic.headers["Content-Type"] == "text/plain; version=0.0.4; charset=utf-8"
    assert "# TYPE http_requests_total counter" in classic.text
    assert openmetrics.status_code == 200
    assert openmetrics.headers["Content-Type"].startswith(f"{OPENMETRICS}; charset=utf-8")
    assert openmetrics.text.endswith("# EOF\n")
    # prometheus-client can't compare that version, so the classic format is served instead.
    assert malformed.status_code == 200
    assert malformed.headers["Content-Type"] == classic.headers["Content-Type"]


def test_answers_are_counted_by_mode_and_outcome() -> None:
    metrics = Metrics()
    answered = AnswerRecord(
        mode=AnswerMode.GENERATED,
        text="Synthetic answer [S1].",
        abstention_reason=None,
        model_name="synthetic-model",
        citations=(),
    )
    declined = AnswerRecord(
        mode=AnswerMode.GENERATED,
        text=None,
        abstention_reason=AbstentionReason.INSUFFICIENT_EVIDENCE,
        model_name="synthetic-model",
        citations=(),
    )

    metrics.count_answer(answered)
    metrics.count_answer(answered)
    metrics.count_answer(declined)

    exposition = metrics.exposition("")[0].decode()
    assert sample_value(exposition, ANSWERS, mode="generated", outcome="answered") == 2
    outcome = "insufficient_evidence"
    assert sample_value(exposition, ANSWERS, mode="generated", outcome=outcome) == 1


def test_indexing_outcomes_are_counted() -> None:
    metrics = Metrics()

    metrics.count_indexing("indexed")
    metrics.count_indexing("indexed")
    metrics.count_indexing("no_text_found")

    exposition = metrics.exposition("")[0].decode()
    assert sample_value(exposition, PROCESSED, outcome="indexed") == 2
    assert sample_value(exposition, PROCESSED, outcome="no_text_found") == 1


def test_each_app_counts_on_its_own(make_app: AppFactory) -> None:
    first = make_app(metrics_enabled=True)
    second = make_app(metrics_enabled=True)

    TestClient(first).get("/health/live")

    labels = {"method": "GET", "route": "/health/live", "status": "200"}
    assert metric_value(first, REQUESTS, **labels) == 1
    assert metric_value(second, REQUESTS, **labels) is None


@pytest.mark.integration
def test_questions_are_counted_by_how_they_were_answered(
    make_db_app: AppFactory, make_client: Callable[[FastAPI], TestClient]
) -> None:
    app = make_db_app()
    client = make_client(app)
    assert register(client).status_code == 201
    workspace = create_workspace(client)

    response = ask(client, workspace["id"], "What does the synthetic policy say?")

    assert response.status_code == 201
    assert response.json()["answer"]["abstention_reason"] == "no_indexed_documents"
    outcome = "no_indexed_documents"
    assert metric_value(app, ANSWERS, mode="search_only", outcome=outcome) == 1
