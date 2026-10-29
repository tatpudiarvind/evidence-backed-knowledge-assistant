"""The background thread that indexes queued documents (Phase 3, D-45)."""

import logging
import threading
from typing import Protocol

logger = logging.getLogger(__name__)

# How often the worker looks for queued documents when nothing wakes it sooner, and how long it
# waits after an error, such as the database being down, before trying again.
POLL_INTERVAL_SECONDS = 5.0
STOP_TIMEOUT_SECONDS = 10.0


class Indexer(Protocol):
    def recover_interrupted(self) -> int: ...

    def process_next(self) -> bool: ...


class IngestionWorker:
    """Indexes queued documents one at a time, in a daemon thread of the API process.

    Uploads and retries wake it at once; it also checks every few seconds, so nothing queued is
    missed. Run a single API process: each process would run its own worker. A document being
    indexed when the server stops stays `processing` until the next start queues it again.
    """

    def __init__(
        self, indexer: Indexer, *, poll_interval_seconds: float = POLL_INTERVAL_SECONDS
    ) -> None:
        self._indexer = indexer
        self._poll_interval = poll_interval_seconds
        self._wake = threading.Event()
        self._stopping = threading.Event()
        self._thread: threading.Thread | None = None

    @property
    def running(self) -> bool:
        return self._thread is not None and self._thread.is_alive()

    def start(self) -> None:
        if self.running:
            return
        self._stopping.clear()
        self._thread = threading.Thread(target=self._run, name="ingestion-worker", daemon=True)
        self._thread.start()

    def notify(self) -> None:
        """Look for queued documents now rather than at the next check."""
        self._wake.set()

    def stop(self, timeout: float = STOP_TIMEOUT_SECONDS) -> None:
        thread = self._thread
        if thread is None:
            return
        self._stopping.set()
        self._wake.set()
        thread.join(timeout)
        if thread.is_alive():
            # It ends with the process; the next start queues its document again.
            logger.warning("The ingestion worker was still indexing a document when stopped")
        self._thread = None

    def _run(self) -> None:
        recovered = False
        failing = False
        while not self._stopping.is_set():
            # Cleared before looking, so a wake-up during the work below is never lost.
            self._wake.clear()
            try:
                if not recovered:
                    self._indexer.recover_interrupted()
                    recovered = True
                found = self._indexer.process_next()
            except Exception as error:
                if not failing:
                    logger.warning(
                        "Indexing paused by an error (%s); trying again every %g s",
                        type(error).__name__,
                        self._poll_interval,
                    )
                failing = True
                # A document claimed before the error is queued again once things work.
                recovered = False
                found = False
            else:
                if failing:
                    logger.info("Indexing resumed")
                failing = False
            if not found:
                self._wake.wait(self._poll_interval)
