import uuid
from collections.abc import Sequence

from sqlalchemy import Select, delete, func, select
from sqlalchemy.orm import Session

from app.db.models import Document, WorkspaceMembership


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
