"""Metrics (Phase 5): counts of requests, answers, and indexed documents, for Prometheus.

They're kept in the API process's memory and start again from zero when it restarts. The API
serves them at `/metrics` only when METRICS_ENABLED is true. Labels hold methods, route
templates, status codes, and outcomes: never IDs, names, or text.
"""

from prometheus_client import CollectorRegistry, Counter, Histogram
from prometheus_client.exposition import (
    CONTENT_TYPE_PLAIN_0_0_4,
    choose_encoder,
    generate_latest,
)

from app.domain.questions import AnswerRecord

# Request durations in seconds, up to the two minutes a local model may take to answer.
REQUEST_DURATION_BUCKETS = (0.005, 0.01, 0.025, 0.05, 0.1, 0.25, 0.5, 1, 2.5, 5, 10, 30, 60, 120)


class Metrics:
    """The API's metrics, in a registry of their own, so each app counts separately."""

    def __init__(self) -> None:
        self.registry = CollectorRegistry()
        self._requests = Counter(
            "http_requests",
            "HTTP requests, by method, route, and status code.",
            ("method", "route", "status"),
            registry=self.registry,
        )
        self._request_duration = Histogram(
            "http_request_duration_seconds",
            "How long HTTP requests took, by method and route.",
            ("method", "route"),
            buckets=REQUEST_DURATION_BUCKETS,
            registry=self.registry,
        )
        self._answers = Counter(
            "knowledge_assistant_answers",
            "Questions answered, by answer mode and outcome: answered, or why it abstained.",
            ("mode", "outcome"),
            registry=self.registry,
        )
        self._documents = Counter(
            "knowledge_assistant_documents_processed",
            "Documents the indexer processed, by outcome: indexed, discarded because the "
            "document changed meanwhile, or the failure code.",
            ("outcome",),
            registry=self.registry,
        )

    def count_request(self, method: str, route: str, status: int | None, seconds: float) -> None:
        """`status` is None for a request that got no response, as when its client left."""
        self._requests.labels(method, route, "none" if status is None else str(status)).inc()
        self._request_duration.labels(method, route).observe(seconds)

    def count_answer(self, answer: AnswerRecord) -> None:
        reason = answer.abstention_reason
        self._answers.labels(answer.mode.value, reason.value if reason else "answered").inc()

    def count_indexing(self, outcome: str) -> None:
        self._documents.labels(outcome).inc()

    def exposition(self, accept_header: str) -> tuple[bytes, str]:
        """The metrics in the format an Accept header asks for, with that format's media type.

        Prometheus asks for its text format or OpenMetrics; anything else gets the classic
        text format.
        """
        try:
            encoder, media_type = choose_encoder(accept_header)
        except (TypeError, ValueError):
            # prometheus-client fails on some malformed versions, such as `version=abc`.
            encoder, media_type = generate_latest, CONTENT_TYPE_PLAIN_0_0_4
        return encoder(self.registry), media_type
