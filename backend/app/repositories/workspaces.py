import uuid
from collections.abc import Sequence

from sqlalchemy import Select, select
from sqlalchemy.orm import Session

from app.db.models import Workspace, WorkspaceMembership
from app.domain.workspaces import WorkspaceRole


def add_workspace(session: Session, name: str, owner_id: uuid.UUID) -> Workspace:
    workspace = Workspace(name=name, owner_id=owner_id)
    session.add(workspace)
    # Insert the workspace first: the membership row refers to it.
    session.flush()
    session.add(
        WorkspaceMembership(
            workspace_id=workspace.id, user_id=owner_id, role=WorkspaceRole.OWNER.value
        )
    )
    return workspace


def _with_role_for(user_id: uuid.UUID) -> Select[tuple[Workspace, str]]:
    return (
        select(Workspace, WorkspaceMembership.role)
        .join(WorkspaceMembership, WorkspaceMembership.workspace_id == Workspace.id)
        .where(WorkspaceMembership.user_id == user_id)
    )


def list_for_member(session: Session, user_id: uuid.UUID) -> Sequence[tuple[Workspace, str]]:
    statement = _with_role_for(user_id).order_by(Workspace.created_at, Workspace.id)
    return session.execute(statement).tuples().all()


def get_for_member(
    session: Session, workspace_id: uuid.UUID, user_id: uuid.UUID, *, lock: bool = False
) -> tuple[Workspace, str] | None:
    statement = _with_role_for(user_id).where(Workspace.id == workspace_id)
    if lock:
        statement = statement.with_for_update(of=Workspace)
    return session.execute(statement).tuples().one_or_none()
