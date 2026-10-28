from fastapi import APIRouter, Request
from fastapi.responses import JSONResponse
from sqlalchemy import Engine
from sqlalchemy.exc import SQLAlchemyError

from app.core.database import check_database

router = APIRouter(tags=["health"])


@router.get("/health/live", summary="Check process liveness")
def live() -> dict[str, str]:
    return {"status": "ok"}


@router.get("/health/ready", summary="Check application readiness", response_model=None)
def ready(request: Request) -> dict[str, str] | JSONResponse:
    engine: Engine = request.app.state.engine
    try:
        check_database(engine)
    except SQLAlchemyError:
        return JSONResponse(
            status_code=503,
            content={"status": "unavailable", "database": "unavailable"},
        )
    return {"status": "ok", "database": "ok"}
