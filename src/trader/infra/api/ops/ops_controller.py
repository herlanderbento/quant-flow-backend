from datetime import datetime, timezone

from fastapi import APIRouter, Depends, status
from fastapi.responses import JSONResponse
from pydantic import BaseModel, ConfigDict
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession

from shared.infra.api.auth_dependencies import AuthContext, require_authenticated
from shared.infra.db.config import settings
from shared.infra.db.database import get_db_session
from trader.infra.db.worker_status_postgres_repository import WorkerStatusPostgresRepository

router = APIRouter(tags=["Operations"])


def worker_state(last_heartbeat_at: datetime | None, stopped_at: datetime | None) -> str:
    if last_heartbeat_at is None:
        return "missing"
    if stopped_at is not None:
        return "stopped"
    age = (datetime.now(timezone.utc) - last_heartbeat_at).total_seconds()
    return "ok" if age <= settings.WORKER_STALE_SECONDS else "stale"


@router.get("/health")
async def health(session: AsyncSession = Depends(get_db_session)):
    """Public liveness summary: no user data, no configuration details."""
    try:
        await session.execute(text("SELECT 1"))
        workers = await WorkerStatusPostgresRepository(session).latest(limit=1)
    except Exception:
        return JSONResponse(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            content={"status": "degraded", "database": "unavailable", "worker": "unknown"},
        )

    latest = workers[0] if workers else None
    state = worker_state(
        latest.last_heartbeat_at if latest else None, latest.stopped_at if latest else None
    )
    healthy = state == "ok"
    return JSONResponse(
        status_code=status.HTTP_200_OK if healthy else status.HTTP_503_SERVICE_UNAVAILABLE,
        content={"status": "ok" if healthy else "degraded", "database": "ok", "worker": state},
    )


class WorkerStatusView(BaseModel):
    """Allow-list of operational fields visible to any authenticated user.

    Excluded on purpose: last_error, audit_details, outcome_counts and bots_last_cycle,
    which carry or reveal other users' trades and activity. Details stay in the logs
    and in trader.infra.ops.soak_report, which only operators with database access run.
    """

    model_config = ConfigDict(extra="forbid")

    worker_id: str
    state: str
    trading_mode: str
    started_at: datetime
    last_heartbeat_at: datetime
    last_cycle_finished_at: datetime | None
    last_market_data_at: datetime | None
    cycles_total: int
    cycle_errors_total: int
    consecutive_failures: int
    max_cycle_gap_seconds: float
    last_audit_at: datetime | None
    audit_ok: bool | None
    stopped_at: datetime | None


class WorkerStatusResponse(BaseModel):
    model_config = ConfigDict(extra="forbid")

    workers: list[WorkerStatusView]


@router.get("/ops/worker-status", response_model=WorkerStatusResponse)
async def worker_status(
    _auth: AuthContext = Depends(require_authenticated),
    session: AsyncSession = Depends(get_db_session),
) -> WorkerStatusResponse:
    """Aggregated health of the most recent worker processes (no per-user data)."""
    rows = await WorkerStatusPostgresRepository(session).latest(limit=5)
    return WorkerStatusResponse(
        workers=[
            WorkerStatusView(
                worker_id=row.worker_id,
                state=worker_state(row.last_heartbeat_at, row.stopped_at),
                trading_mode=row.trading_mode,
                started_at=row.started_at,
                last_heartbeat_at=row.last_heartbeat_at,
                last_cycle_finished_at=row.last_cycle_finished_at,
                last_market_data_at=row.last_market_data_at,
                cycles_total=row.cycles_total,
                cycle_errors_total=row.cycle_errors_total,
                consecutive_failures=row.consecutive_failures,
                max_cycle_gap_seconds=float(row.max_cycle_gap_seconds),
                last_audit_at=row.last_audit_at,
                audit_ok=None if row.last_audit_at is None else row.audit_issues == 0,
                stopped_at=row.stopped_at,
            )
            for row in rows
        ]
    )
