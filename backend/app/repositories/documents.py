import uuid
from collections.abc import Sequence

from sqlalchemy import Select, delete, func, select, update
from sqlalchemy.orm import Session

from app.db.models import Document, WorkspaceMembership
from app.domain.documents import DocumentStatus


def _visible_to(user_id: uuid.UUID) -> Select[tuple[Document]]:
    """Documents in workspaces the user belongs to. A guessed document ID matches nothing else."""
    return select(Document).join(
        WorkspaceMembership,
        (WorkspaceMembership.workspace_id == Document.workspace_id)
        & (WorkspaceMembership.user_id == user_id),
    )


def list_for_member(
    session: Session, workspace_id: uuid.UUID, user_id: uuid.UUID
) -> Sequence[Document]:
    statement = (
        _visible_to(user_id)
        .where(Document.workspace_id == workspace_id)
        .order_by(Document.created_at.desc(), Document.id.desc())
    )
    return session.scalars(statement).all()


def get_for_member(
    session: Session, document_id: uuid.UUID, user_id: uuid.UUID, *, lock: bool = False
) -> Document | None:
    statement = _visible_to(user_id).where(Document.id == document_id)
    if lock:
        statement = statement.with_for_update(of=Document)
    return session.scalar(statement)


def count_in_workspace(session: Session, workspace_id: uuid.UUID) -> int:
    statement = select(func.count()).select_from(Document)
    return session.scalar(statement.where(Document.workspace_id == workspace_id)) or 0


def add(session: Session, document: Document) -> None:
    session.add(document)


def delete_by_id(session: Session, document_id: uuid.UUID) -> None:
    session.execute(delete(Document).where(Document.id == document_id))


# Indexing runs outside any user's request, so these queries aren't limited to one user.


def get_by_id(session: Session, document_id: uuid.UUID, *, lock: bool = False) -> Document | None:
    statement = select(Document).where(Document.id == document_id)
    if lock:
        statement = statement.with_for_update()
    return session.scalar(statement)


def claim_next_queued(session: Session) -> Document | None:
    """Lock the oldest queued document, skipping any another transaction has locked."""
    statement = (
        select(Document)
        .where(Document.status == DocumentStatus.QUEUED.value)
        .order_by(Document.created_at, Document.id)
        .limit(1)
        .with_for_update(skip_locked=True)
    )
    return session.scalar(statement)


def requeue_processing(session: Session) -> int:
    """Queue again any document left `processing`, as when the server stopped mid-way."""
    statement = (
        update(Document)
        .where(Document.status == DocumentStatus.PROCESSING.value)
        .values(status=DocumentStatus.QUEUED.value)
        .returning(Document.id)
    )
    return len(session.scalars(statement).all())
