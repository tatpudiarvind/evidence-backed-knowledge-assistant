import uuid
from dataclasses import dataclass

from sqlalchemy.orm import Session

from app.core.errors import AppError
from app.db.models import User, Workspace
from app.domain.workspaces import WorkspaceRole
from app.repositories import workspaces as workspace_repository


@dataclass(frozen=True)
class WorkspaceAccess:
    workspace: Workspace
    role: WorkspaceRole


def create_workspace(session: Session, user: User, name: str) -> WorkspaceAccess:
    workspace = workspace_repository.add_workspace(session, name, user.id)
    session.commit()
    return WorkspaceAccess(workspace, WorkspaceRole.OWNER)


def list_workspaces(session: Session, user: User) -> list[WorkspaceAccess]:
    return [
        WorkspaceAccess(workspace, WorkspaceRole(role))
        for workspace, role in workspace_repository.list_for_member(session, user.id)
    ]


def require_workspace(
    session: Session, user: User, workspace_id: uuid.UUID, *, lock: bool = False
) -> WorkspaceAccess:
    """Return the workspace if the user is a member. Otherwise, act as if it doesn't exist."""
    found = workspace_repository.get_for_member(session, workspace_id, user.id, lock=lock)
    if found is None:
        raise AppError(
            404,
            "workspace_not_found",
            "This workspace doesn't exist, or you don't have access to it.",
        )
    workspace, role = found
    return WorkspaceAccess(workspace, WorkspaceRole(role))
