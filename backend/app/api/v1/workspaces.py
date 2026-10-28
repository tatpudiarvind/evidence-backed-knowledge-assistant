from fastapi import APIRouter

from app.api.deps import CurrentUser, DbSession
from app.api.v1.schemas import WorkspaceCreateRequest, WorkspaceList, WorkspaceOut
from app.services import workspaces as workspace_service

router = APIRouter(prefix="/workspaces", tags=["workspaces"])


def _workspace_out(access: workspace_service.WorkspaceAccess) -> WorkspaceOut:
    workspace = access.workspace
    return WorkspaceOut(
        id=workspace.id, name=workspace.name, role=access.role, created_at=workspace.created_at
    )


@router.post("", status_code=201, summary="Create a workspace")
def create_workspace(
    body: WorkspaceCreateRequest, user: CurrentUser, session: DbSession
) -> WorkspaceOut:
    return _workspace_out(workspace_service.create_workspace(session, user, body.name))


@router.get("", summary="List your workspaces")
def list_workspaces(user: CurrentUser, session: DbSession) -> WorkspaceList:
    accesses = workspace_service.list_workspaces(session, user)
    return WorkspaceList(items=[_workspace_out(access) for access in accesses])
