"""Transactional queue operations for indexing jobs."""

import random
import uuid
from datetime import timedelta

from sqlalchemy import func, select, text, update
from sqlalchemy.dialects.postgresql import insert
from sqlalchemy.orm import Session

from app.db.models import Document, Job
from app.domain.indexing import IndexingFailure

LEASE_SECONDS = 60
MAX_ATTEMPTS = 5
TEMPORARY_FAILURES = {
    IndexingFailure.EMBEDDING_UNAVAILABLE.value,
    IndexingFailure.EMBEDDING_FAILED.value,
    IndexingFailure.INGESTION_FAILED.value,
    "worker_crashed",
    "parse_timeout",
}


def enqueue(session: Session, document_id: uuid.UUID) -> None:
    key = f"index_document:{document_id}"
    statement = (
        insert(Job)
        .values(
            id=uuid.uuid4(),
            kind="index_document",
            payload={"document_id": str(document_id)},
            status="queued",
            attempts=0,
            max_attempts=MAX_ATTEMPTS,
            dedupe_key=key,
        )
        .on_conflict_do_nothing(
            index_elements=[Job.dedupe_key],
            index_where=Job.status.in_(["queued", "running"]),
        )
    )
    session.execute(statement)
    session.execute(
        text("SELECT pg_notify('indexing_jobs', :payload)"), {"payload": str(document_id)}
    )


def claim(session: Session, worker_id: str) -> Job | None:
    candidate = (
        select(Job.id)
        .where(Job.status == "queued", Job.run_after <= func.now())
        .order_by(Job.run_after, Job.created_at, Job.id)
        .limit(1)
        .with_for_update(skip_locked=True)
        .scalar_subquery()
    )
    return session.scalar(
        update(Job)
        .where(Job.id == candidate, Job.status == "queued")
        .values(
            status="running",
            attempts=Job.attempts + 1,
            locked_by=worker_id,
            locked_until=func.now() + timedelta(seconds=LEASE_SECONDS),
            updated_at=func.now(),
        )
        .returning(Job)
    )


def heartbeat(session: Session, job_id: uuid.UUID, worker_id: str) -> bool:
    result = session.execute(
        update(Job)
        .where(
            Job.id == job_id,
            Job.status == "running",
            Job.locked_by == worker_id,
            Job.locked_until > func.now(),
        )
        .values(locked_until=func.now() + timedelta(seconds=LEASE_SECONDS), updated_at=func.now())
    )
    return result.rowcount == 1


def finish(
    session: Session,
    job_id: uuid.UUID,
    worker_id: str,
    *,
    error_code: str | None = None,
    permanent: bool = False,
) -> bool:
    job = session.scalar(
        select(Job)
        .where(
            Job.id == job_id,
            Job.status == "running",
            Job.locked_by == worker_id,
            Job.locked_until > func.now(),
        )
        .with_for_update()
    )
    if job is None:
        return False
    if error_code is None:
        job.status = "succeeded"
        job.locked_by = None
        job.locked_until = None
    elif permanent or error_code not in TEMPORARY_FAILURES or job.attempts >= job.max_attempts:
        job.status = "failed"
        job.last_error_code = error_code
        job.locked_by = None
        job.locked_until = None
    else:
        delay = min(300, 5 * (2 ** max(0, job.attempts - 1)))
        delay = max(1, delay * random.uniform(0.8, 1.2))
        job.status = "queued"
        job.last_error_code = error_code
        job.run_after = func.now() + timedelta(seconds=delay)
        job.locked_by = None
        job.locked_until = None
        session.execute(
            text("SELECT pg_notify('indexing_jobs', :payload)"), {"payload": str(job.id)}
        )
    session.flush()
    return True


def reap_expired(session: Session) -> int:
    expired = session.scalars(
        select(Job)
        .where(Job.status == "running", Job.locked_until <= func.now())
        .with_for_update(skip_locked=True)
    ).all()
    for job in expired:
        try:
            document_id = uuid.UUID(job.payload["document_id"])
        except (KeyError, ValueError):
            document_id = None
        document = session.get(Document, document_id) if document_id else None
        job.locked_by = None
        job.locked_until = None
        job.last_error_code = "lease_expired"
        if job.attempts >= job.max_attempts:
            job.status = "failed"
            if document is not None:
                document.status = "failed"
                document.failure_code = "ingestion_failed"
                document.failure_message = "Indexing failed unexpectedly. Try again."
        else:
            job.status = "queued"
            if document is not None:
                document.status = "queued"
            job.run_after = func.now()
            session.execute(
                text("SELECT pg_notify('indexing_jobs', :payload)"), {"payload": str(job.id)}
            )
    return len(expired)


def cancel_for_document(session: Session, document_id: uuid.UUID) -> None:
    session.execute(
        update(Job)
        .where(
            Job.dedupe_key == f"index_document:{document_id}", Job.status.in_(["queued", "running"])
        )
        .values(status="cancelled", locked_by=None, locked_until=None, updated_at=func.now())
    )
