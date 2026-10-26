from fastapi import APIRouter
from fastapi.responses import JSONResponse
from sqlalchemy.exc import SQLAlchemyError

from app.core.database import check_database

router = APIRouter(tags=["health"])


@router.get("/health/live", summary="Check process liveness")
def live() -> dict[str, str]:
    return {"status": "ok"}


@router.get("/health/ready", summary="Check application readiness", response_model=None)
def ready() -> dict[str, str] | JSONResponse:
    try:
        check_database()
    except SQLAlchemyError:
        return JSONResponse(
            status_code=503,
            content={"status": "unavailable", "database": "unavailable"},
        )
    return {"status": "ok", "database": "ok"}
