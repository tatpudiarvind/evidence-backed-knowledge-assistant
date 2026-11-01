"""Indexing: turns queued documents into searchable chunks (Phase 3, spec section 6.1).

A document goes from `queued` to `processing`, then to `ready` with its chunks saved, or to
`failed` with a code and a message that are safe to show. A document deleted part-way through
is left alone. Logs name documents by ID only, never quoting their text.
"""

import json
import logging
import os
import subprocess
import sys
import threading
import uuid
from collections.abc import Callable, Sequence
from dataclasses import dataclass

from sqlalchemy import select
from sqlalchemy.orm import Session, sessionmaker

from app.core.config import Settings
from app.core.metrics import Metrics
from app.db.models import Document, Job
from app.domain.documents import DocumentStatus
from app.domain.indexing import (
    IndexingError,
    IndexingFailure,
    TextBlock,
    TextChunk,
    chunk_blocks,
    normalize_blocks,
)
from app.providers.embeddings import EmbeddingProvider, EmbeddingUnavailableError, check_vectors
from app.providers.parsers import ParseLimits
from app.providers.storage import DocumentStorage
from app.repositories import chunks as chunk_repository
from app.repositories import documents as document_repository
from app.repositories import jobs as job_repository

logger = logging.getLogger(__name__)


@dataclass(frozen=True)
class _Job:
    job_id: uuid.UUID
    document_id: uuid.UUID
    storage_key: str
    mime_type: str


class DocumentIndexer:
    """Indexes one queued document at a time: read, split into chunks, embed, and save."""

    def __init__(
        self,
        session_factory: sessionmaker[Session],
        storage: DocumentStorage,
        embeddings: EmbeddingProvider,
        settings: Settings,
        *,
        metrics: Metrics | None = None,
    ) -> None:
        self._session_factory = session_factory
        self._storage = storage
        self._embeddings = embeddings
        self._metrics = metrics
        self._limits = ParseLimits(
            max_pages=settings.max_document_pages,
            max_characters=settings.max_document_characters,
            timeout_seconds=settings.parse_timeout_seconds,
        )
        self._chunk_size = settings.chunk_size_characters
        self._chunk_overlap = settings.chunk_overlap_characters

    def listen_for_jobs(self, stopped: threading.Event, wake: Callable[[], None]) -> None:
        """Listen on a dedicated autocommit connection; polling remains the recovery path."""
        engine = self._session_factory.kw["bind"]
        while not stopped.is_set():
            try:
                with engine.connect().execution_options(isolation_level="AUTOCOMMIT") as connection:
                    connection.exec_driver_sql("LISTEN indexing_jobs")
                    raw_connection = connection.connection.driver_connection
                    while not stopped.is_set():
                        notifications = raw_connection.notifies(timeout=5, stop_after=1)
                        if next(notifications, None) is not None:
                            wake()
            except Exception as error:
                logger.warning(
                    "The indexing notification listener paused (%s)", type(error).__name__
                )
                stopped.wait(5)

    def recover_interrupted(self) -> int:
        """Reap expired leases; unlike the old startup recovery, live workers retain leases."""
        with self._session_factory() as session:
            count = job_repository.reap_expired(session)
            active = session.execute(
                select(Job.payload, Job.status).where(Job.status.in_(["queued", "running"]))
            ).all()
            active_ids = {
                payload.get("document_id")
                for payload, _status in active
                if isinstance(payload, dict)
            }
            running_ids = {
                payload.get("document_id")
                for payload, status in active
                if status == "running" and isinstance(payload, dict)
            }
            orphaned = session.scalars(
                select(Document).where(
                    Document.status.in_(
                        [DocumentStatus.QUEUED.value, DocumentStatus.PROCESSING.value]
                    )
                )
            ).all()
            for document in orphaned:
                document_key = str(document.id)
                if document.status == DocumentStatus.PROCESSING and document_key not in running_ids:
                    document.status = DocumentStatus.QUEUED.value
                    count += 1
                if document_key not in active_ids:
                    document.status = DocumentStatus.QUEUED.value
                    job_repository.enqueue(session, document.id)
                    count += 1
            session.commit()
        return count

    def process_next(self) -> bool:
        """Claim and process one durable job. Claims commit before parsing or embedding."""
        self.recover_interrupted()
        worker_id = str(uuid.uuid4())
        with self._session_factory() as session:
            job = job_repository.claim(session, worker_id)
            if job is None:
                return False
            try:
                document_id = uuid.UUID(job.payload["document_id"])
            except (KeyError, ValueError):
                job_repository.finish(
                    session, job.id, worker_id, error_code="ingestion_failed", permanent=True
                )
                session.commit()
                return True
            document = document_repository.get_by_id(session, document_id, lock=True)
            if document is None or document.status == DocumentStatus.DELETING:
                job.status = "cancelled"
                job.locked_by = None
                job.locked_until = None
                session.commit()
                return True
            document.status = DocumentStatus.PROCESSING.value
            payload = _Job(job.id, document.id, document.storage_key, document.mime_type)
            session.commit()
        heartbeat_stop = threading.Event()
        heartbeat = threading.Thread(
            target=self._heartbeat, args=(payload.job_id, worker_id, heartbeat_stop), daemon=True
        )
        heartbeat.start()
        try:
            chunks = self._read_chunks(payload)
            vectors = self._embed(chunks)
        except IndexingError as error:
            logger.warning(
                "Indexing document %s failed: %s", payload.document_id, error.failure.value
            )
            self._record_failure(
                payload,
                worker_id,
                error,
                permanent=error.failure.value not in job_repository.TEMPORARY_FAILURES,
            )
        except Exception as error:
            logger.warning(
                "Indexing document %s failed unexpectedly (%s)",
                payload.document_id,
                type(error).__name__,
            )
            self._record_failure(
                payload, worker_id, IndexingError(IndexingFailure.INGESTION_FAILED), permanent=False
            )
        else:
            try:
                self._save(payload, worker_id, chunks, vectors)
            except Exception as error:
                logger.warning(
                    "Indexing document %s failed unexpectedly (%s)",
                    payload.document_id,
                    type(error).__name__,
                )
                self._record_failure(
                    payload,
                    worker_id,
                    IndexingError(IndexingFailure.INGESTION_FAILED),
                    permanent=False,
                )
        finally:
            heartbeat_stop.set()
            heartbeat.join(timeout=2)
        return True

    def _heartbeat(self, job_id: uuid.UUID, worker_id: str, stopped: threading.Event) -> None:
        while not stopped.wait(15):
            try:
                with self._session_factory() as session:
                    job_repository.heartbeat(session, job_id, worker_id)
                    session.commit()
            except Exception:
                logger.warning("Indexing lease heartbeat failed (%s)", job_id)

    def _read_chunks(self, job: _Job) -> list[TextChunk]:
        try:
            handle = self._storage.open(job.storage_key)
        except FileNotFoundError:
            raise IndexingError(IndexingFailure.FILE_MISSING) from None
        path, temporary = self._storage.create_temp_file()
        try:
            with handle, temporary:
                temporary.write(handle.read())
            env = {
                key: value
                for key, value in os.environ.items()
                if key in {"PATH", "SYSTEMROOT", "WINDIR", "TEMP", "TMP"}
            }
            try:
                result = subprocess.run(
                    [
                        sys.executable,
                        "-m",
                        "app.parser_process",
                        str(path),
                        job.mime_type,
                        str(self._limits.max_pages),
                        str(self._limits.max_characters),
                        str(self._limits.timeout_seconds),
                    ],
                    capture_output=True,
                    text=True,
                    timeout=self._limits.timeout_seconds,
                    env=env,
                    cwd=str(__import__("pathlib").Path(__file__).resolve().parents[2]),
                    check=False,
                )
            except subprocess.TimeoutExpired:
                raise IndexingError(IndexingFailure.PARSE_TIMEOUT) from None
            if result.returncode != 0:
                raise IndexingError(IndexingFailure.INGESTION_FAILED)
            blocks = json.loads(result.stdout)
            if isinstance(blocks, dict) and "error" in blocks:
                try:
                    failure = IndexingFailure(blocks["error"])
                except ValueError:
                    failure = IndexingFailure.INGESTION_FAILED
                raise IndexingError(failure)
            normalized = normalize_blocks(
                TextBlock(item["text"], item.get("page_number"), item.get("section"))
                for item in blocks
            )
            chunks = chunk_blocks(normalized, self._chunk_size, self._chunk_overlap)
            if not chunks:
                raise IndexingError(IndexingFailure.NO_TEXT_FOUND)
            return chunks
        finally:
            path.unlink(missing_ok=True)

    def _save(
        self,
        job: _Job,
        worker_id: str,
        chunks: Sequence[TextChunk],
        vectors: Sequence[Sequence[float]],
    ) -> bool:
        with self._session_factory() as session:
            locked = session.scalar(
                __import__("sqlalchemy")
                .select(Job)
                .where(
                    Job.id == job.job_id,
                    Job.status == "running",
                    Job.locked_by == worker_id,
                    Job.locked_until > __import__("sqlalchemy").func.now(),
                )
                .with_for_update()
            )
            document = document_repository.get_by_id(session, job.document_id, lock=True)
            if locked is None or document is None or document.status != DocumentStatus.PROCESSING:
                session.rollback()
                self._count("discarded")
                return False
            chunk_repository.replace_for_document(session, job.document_id, chunks, vectors)
            document.status = DocumentStatus.READY.value
            document.failure_code = None
            document.failure_message = None
            job_repository.finish(session, job.job_id, worker_id)
            session.commit()
        self._count("indexed")
        return True

    def _record_failure(
        self, job: _Job, worker_id: str, error: IndexingError, *, permanent: bool
    ) -> None:
        with self._session_factory() as session:
            db_job = session.get(Job, job.job_id)
            if db_job is None or db_job.locked_by != worker_id or db_job.status != "running":
                self._count("discarded")
                return
            accepted = job_repository.finish(
                session, job.job_id, worker_id, error_code=error.failure.value, permanent=permanent
            )
            document = document_repository.get_by_id(session, job.document_id, lock=True)
            if accepted and document is not None:
                db_job = session.get(Job, job.job_id)
                if db_job and db_job.status == "failed":
                    document.status = DocumentStatus.FAILED.value
                    document.failure_code = error.failure.value
                    document.failure_message = error.message
                elif db_job and db_job.status == "queued":
                    document.status = DocumentStatus.QUEUED.value
            session.commit()
        if accepted:
            self._count(error.failure.value)

    def _embed(self, chunks: Sequence[TextChunk]) -> list[list[float]]:
        try:
            embeddings = self._embeddings.embed_documents([chunk.text for chunk in chunks])
        except EmbeddingUnavailableError:
            raise IndexingError(IndexingFailure.EMBEDDING_UNAVAILABLE) from None
        except Exception as error:
            raise IndexingError(IndexingFailure.EMBEDDING_FAILED) from error
        if not check_vectors(embeddings, len(chunks)):
            raise IndexingError(IndexingFailure.EMBEDDING_FAILED)
        return embeddings

    def _count(self, outcome: str) -> None:
        if self._metrics is not None:
            self._metrics.count_indexing(outcome)
