from fastapi import APIRouter, Depends

from app.api.deps import require_csrf_header
from app.api.v1 import auth, documents, workspaces
from app.api.v1.schemas import ErrorResponse

router = APIRouter(
    prefix="/api/v1",
    dependencies=[Depends(require_csrf_header)],
    responses={
        "4XX": {"model": ErrorResponse, "description": "Client error"},
        "5XX": {"model": ErrorResponse, "description": "Server error"},
    },
)
router.include_router(auth.router)
router.include_router(workspaces.router)
router.include_router(documents.router)
