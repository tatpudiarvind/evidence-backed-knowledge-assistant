"""The background indexing thread (P3-07), driven by a stand-in indexer."""

import logging
import threading

import pytest
from fastapi.testclient import TestClient

from app.workers.ingestion import IngestionWorker
from tests.conftest import AppFactory

# Generous, so a slow machine never fails a test; each wait normally ends within milliseconds.
WAIT_SECONDS = 5


class FakeIndexer:
    """Hands out queued documents, recording each call the worker makes.

    `idle` is set whenever it finds nothing queued. With a `gate`, it waits for the gate to
    open before each document, setting `started` first.
    """

    def __init__(self, queued: int = 0) -> None:
        self.calls: list[str] = []
        self.errors: list[Exception] = []
        self.idle = threading.Event()
        self.started = threading.Event()
        self.gate: threading.Event | None = None
        self._queued = queued
        self._lock = threading.Lock()

    def queue(self, count: int = 1) -> None:
        with self._lock:
            self._queued += count

    def recover_interrupted(self) -> int:
        with self._lock:
            self.calls.append("recover")
        return 0

    def process_next(self) -> bool:
        if self.gate is not None:
            self.started.set()
            self.gate.wait()
        with self._lock:
            if self.errors:
                self.calls.append("error")
                raise self.errors.pop(0)
            if self._queued:
                self._queued -= 1
                self.calls.append("indexed")
                return True
            self.calls.append("idle")
        self.idle.set()
        return False


def _worker_threads() -> list[threading.Thread]:
    return [thread for thread in threading.enumerate() if thread.name == "ingestion-worker"]


def test_recovers_interrupted_work_then_indexes_everything_queued() -> None:
    indexer = FakeIndexer(queued=3)
    worker = IngestionWorker(indexer, poll_interval_seconds=60)

    worker.start()
    try:
        assert indexer.idle.wait(WAIT_SECONDS)
    finally:
        worker.stop()

    assert indexer.calls == ["recover", "indexed", "indexed", "indexed", "idle"]
    assert not worker.running


def test_notify_wakes_the_worker_at_once() -> None:
    indexer = FakeIndexer()
    # Without the wake-up, the next check would come only after a minute.
    worker = IngestionWorker(indexer, poll_interval_seconds=60)
    worker.start()
    try:
        assert indexer.idle.wait(WAIT_SECONDS)
        indexer.idle.clear()
        indexer.queue()
        worker.notify()
        assert indexer.idle.wait(WAIT_SECONDS)
    finally:
        worker.stop()

    assert indexer.calls == ["recover", "idle", "indexed", "idle"]


def test_errors_pause_indexing_until_it_works_again(caplog: pytest.LogCaptureFixture) -> None:
    caplog.set_level(logging.INFO, logger="app.workers.ingestion")
    indexer = FakeIndexer(queued=1)
    indexer.errors = [RuntimeError("synthetic secret"), RuntimeError("synthetic secret")]
    worker = IngestionWorker(indexer, poll_interval_seconds=0.01)

    worker.start()
    try:
        assert indexer.idle.wait(WAIT_SECONDS)
    finally:
        worker.stop()

    # Each error makes the worker look again for documents left half-indexed.
    expected = ["recover", "error", "recover", "error", "recover", "indexed", "idle"]
    assert indexer.calls[: len(expected)] == expected
    assert set(indexer.calls[len(expected) :]) <= {"idle"}
    messages = [record.getMessage() for record in caplog.records]
    assert messages == [
        "Indexing paused by an error (RuntimeError); trying again every 0.01 s",
        "Indexing resumed",
    ]
    assert caplog.records[0].levelno == logging.WARNING


def test_starting_twice_runs_one_thread_and_it_can_start_again_after_stopping() -> None:
    indexer = FakeIndexer()
    worker = IngestionWorker(indexer, poll_interval_seconds=60)

    worker.start()
    worker.start()
    try:
        assert indexer.idle.wait(WAIT_SECONDS)
        assert worker.running
        assert len(_worker_threads()) == 1
    finally:
        worker.stop()
    assert not worker.running
    assert _worker_threads() == []

    indexer.idle.clear()
    worker.start()
    try:
        assert indexer.idle.wait(WAIT_SECONDS)
    finally:
        worker.stop()
    assert indexer.calls == ["recover", "idle", "recover", "idle"]


def test_stopping_a_worker_that_never_started_does_nothing() -> None:
    worker = IngestionWorker(FakeIndexer())

    worker.stop()

    assert not worker.running


def test_stopping_does_not_wait_forever_for_a_slow_document(
    caplog: pytest.LogCaptureFixture,
) -> None:
    indexer = FakeIndexer(queued=1)
    indexer.gate = threading.Event()
    worker = IngestionWorker(indexer, poll_interval_seconds=60)
    worker.start()
    assert indexer.started.wait(WAIT_SECONDS)
    [thread] = _worker_threads()

    worker.stop(timeout=0.05)

    assert not worker.running
    assert "still indexing a document when stopped" in caplog.text
    # Once its document is done, the thread notices it was stopped and ends.
    indexer.gate.set()
    thread.join(WAIT_SECONDS)
    assert not thread.is_alive()
    assert indexer.calls == ["recover", "indexed"]


def test_the_api_leaves_the_worker_off_when_disabled(make_app: AppFactory) -> None:
    app = make_app(ingestion_worker_enabled=False)

    with TestClient(app):
        assert not app.state.ingestion_worker.running
