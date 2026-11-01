from fastapi import APIRouter, Request
from fastapi.responses import JSONResponse, PlainTextResponse, Response
from sqlalchemy import Engine, func, select
from sqlalchemy.exc import SQLAlchemyError

from app.api.deps import MetricsDep
from app.core.database import check_database
from app.db.models import Job

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
    session_factory = request.app.state.session_factory
    try:
        with session_factory() as session:
            rows = session.execute(select(Job.status, func.count()).group_by(Job.status)).all()
            oldest = session.scalar(
                select(func.extract("epoch", func.now() - func.min(Job.created_at))).where(
                    Job.status == "queued"
                )
            )
        metrics.set_job_metrics({status: count for status, count in rows}, float(oldest or 0))
    except SQLAlchemyError:
        metrics.set_job_metrics({}, 0)
    body, media_type = metrics.exposition(request.headers.get("accept", ""))
    return Response(body, media_type=media_type)
