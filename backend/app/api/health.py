from fastapi import APIRouter, Request
from fastapi.responses import JSONResponse, PlainTextResponse, Response
from sqlalchemy import Engine
from sqlalchemy.exc import SQLAlchemyError

from app.api.deps import MetricsDep
from app.core.database import check_database

router = APIRouter(tags=["health"])
# Included only when METRICS_ENABLED is true. Anyone who can reach the API can read them.
metrics_router = APIRouter(tags=["health"])


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


@metrics_router.get(
    "/metrics",
    summary="Read the API's metrics in Prometheus's text format or OpenMetrics",
    response_class=PlainTextResponse,
)
def read_metrics(request: Request, metrics: MetricsDep) -> Response:
    body, media_type = metrics.exposition(request.headers.get("accept", ""))
    return Response(body, media_type=media_type)
