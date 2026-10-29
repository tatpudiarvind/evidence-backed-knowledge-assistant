"""The background thread that deletes questions three days after they're asked (Phase 4)."""

import logging
import threading

from sqlalchemy.orm import Session, sessionmaker

from app.repositories import questions as question_repository

logger = logging.getLogger(__name__)

CLEANUP_INTERVAL_SECONDS = 3600.0
STOP_TIMEOUT_SECONDS = 10.0


class QuestionCleanupWorker:
    """Deletes expired questions, with their answers and citations, when the API starts and
    then every hour, in a daemon thread of the API process.

    Question history hides expired questions as soon as they expire, so the time between runs,
    or while the API is stopped, only delays when their rows are deleted.
    """

    def __init__(
        self,
        session_factory: sessionmaker[Session],
        *,
        interval_seconds: float = CLEANUP_INTERVAL_SECONDS,
    ) -> None:
        self._session_factory = session_factory
        self._interval = interval_seconds
        self._stopping = threading.Event()
        self._thread: threading.Thread | None = None

    @property
    def running(self) -> bool:
        return self._thread is not None and self._thread.is_alive()

    def start(self) -> None:
        if self.running:
            return
        self._stopping.clear()
        self._thread = threading.Thread(target=self._run, name="question-cleanup", daemon=True)
        self._thread.start()

    def stop(self, timeout: float = STOP_TIMEOUT_SECONDS) -> None:
        thread = self._thread
        if thread is None:
            return
        self._stopping.set()
        thread.join(timeout)
        self._thread = None

    def run_once(self) -> int:
        with self._session_factory() as session:
            deleted = question_repository.delete_expired(session)
            session.commit()
        if deleted:
            logger.info("Deleted %d expired questions", deleted)
        return deleted

    def _run(self) -> None:
        while not self._stopping.is_set():
            try:
                self.run_once()
            except Exception as error:
                logger.warning(
                    "Deleting expired questions failed (%s); trying again in %g s",
                    type(error).__name__,
                    self._interval,
                )
            self._stopping.wait(self._interval)
