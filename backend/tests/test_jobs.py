"""PostgreSQL integration tests for the durable indexing queue."""

import uuid
from concurrent.futures import ThreadPoolExecutor

import pytest
from sqlalchemy import func, select, text, update

from app.db.models import Job
from app.repositories import jobs

pytestmark = pytest.mark.integration


def _queued(session_factory, document_id: uuid.UUID, *, max_attempts: int = 5) -> uuid.UUID:
    job_id = uuid.uuid4()
    with session_factory() as session:
        session.add(
            Job(
                id=job_id,
                kind="index_document",
                payload={"document_id": str(document_id)},
                status="queued",
                attempts=0,
                max_attempts=max_attempts,
                dedupe_key=f"index_document:{document_id}",
            )
        )
        session.commit()
    return job_id


def test_enqueue_deduplicates_and_rollback_removes_job(db_app) -> None:
    factory = db_app.state.session_factory
    document_id = uuid.uuid4()
    with factory() as session:
        jobs.enqueue(session, document_id)
        jobs.enqueue(session, document_id)
        session.commit()
    with factory() as session:
        assert session.scalar(select(func.count()).select_from(Job)) == 1
        session.rollback()
    rolled_back_id = uuid.uuid4()
    with factory() as session:
        jobs.enqueue(session, rolled_back_id)
        session.rollback()
    with factory() as session:
        assert (
            session.scalar(
                select(Job.id).where(Job.dedupe_key == f"index_document:{rolled_back_id}")
            )
            is None
        )


def test_concurrent_claims_return_distinct_jobs(db_app) -> None:
    factory = db_app.state.session_factory
    _queued(factory, uuid.uuid4())
    _queued(factory, uuid.uuid4())

    def claim_one() -> uuid.UUID | None:
        worker_id = str(uuid.uuid4())
        with factory() as session:
            job = jobs.claim(session, worker_id)
            session.commit()
            return job.id if job else None

    with ThreadPoolExecutor(max_workers=2) as pool:
        claimed = list(pool.map(lambda _: claim_one(), range(2)))
    assert None not in claimed
    assert len(set(claimed)) == 2


def test_expired_lease_is_reclaimed_and_old_worker_is_fenced(db_app) -> None:
    factory = db_app.state.session_factory
    job_id = _queued(factory, uuid.uuid4())
    first_worker = str(uuid.uuid4())
    with factory() as session:
        first = jobs.claim(session, first_worker)
        session.commit()
        assert first and first.id == job_id
    with factory() as session:
        session.execute(
            update(Job)
            .where(Job.id == job_id)
            .values(locked_until=func.now() - text("interval '2 minutes'"))
        )
        jobs.reap_expired(session)
        session.commit()
    second_worker = str(uuid.uuid4())
    with factory() as session:
        second = jobs.claim(session, second_worker)
        assert second and second.id == job_id
        assert not jobs.finish(session, job_id, first_worker)
        session.rollback()


def test_max_attempts_turns_temporary_failure_terminal(db_app) -> None:
    factory = db_app.state.session_factory
    job_id = _queued(factory, uuid.uuid4(), max_attempts=1)
    worker = str(uuid.uuid4())
    with factory() as session:
        assert jobs.claim(session, worker)
        assert jobs.finish(session, job_id, worker, error_code="embedding_unavailable")
        session.commit()
    with factory() as session:
        job = session.get(Job, job_id)
        assert job and job.status == "failed" and job.attempts == 1


def test_delete_cancels_unfinished_jobs(db_app) -> None:
    factory = db_app.state.session_factory
    document_id = uuid.uuid4()
    _queued(factory, document_id)
    with factory() as session:
        jobs.cancel_for_document(session, document_id)
        session.commit()
    with factory() as session:
        job = session.scalar(select(Job).where(Job.dedupe_key == f"index_document:{document_id}"))
        assert job and job.status == "cancelled"
