"""Run the durable indexing and retention workers: `python -m app.worker`."""

import logging
import signal
import threading

from app.core.config import get_settings
from app.factory import create_app


def main() -> None:
    logging.basicConfig(
        level=logging.INFO, format="%(asctime)s %(levelname)s %(name)s: %(message)s"
    )
    settings = get_settings()
    app = create_app(
        settings.model_copy(
            update={"ingestion_worker_enabled": False, "question_cleanup_enabled": False}
        )
    )
    stopping = threading.Event()
    signal.signal(signal.SIGTERM, lambda *_: stopping.set())
    signal.signal(signal.SIGINT, lambda *_: stopping.set())
    worker = app.state.ingestion_worker
    cleanup = app.state.question_cleanup
    worker.start()
    if settings.question_cleanup_enabled:
        cleanup.start()
    try:
        stopping.wait()
    finally:
        worker.stop()
        cleanup.stop()
        app.state.engine.dispose()


if __name__ == "__main__":
    main()
