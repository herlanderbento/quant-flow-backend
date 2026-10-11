from datetime import datetime

from sqlalchemy import desc, select
from sqlalchemy.dialects.postgresql import insert
from sqlalchemy.ext.asyncio import AsyncSession

from trader.application.worker_metrics import WorkerMetrics
from trader.infra.db.sql_models import WorkerStatusModel

PERSISTED_FIELDS = (
    "trading_mode", "hostname", "started_at", "last_cycle_started_at",
    "last_cycle_finished_at", "last_market_data_at", "cycles_total",
    "cycle_errors_total", "consecutive_failures", "max_cycle_gap_seconds",
    "bots_last_cycle", "outcome_counts", "last_error", "last_audit_at",
    "audit_issues", "audit_details", "stopped_at",
)


class WorkerStatusPostgresRepository:
    def __init__(self, session: AsyncSession):
        self.session = session

    async def save(self, metrics: WorkerMetrics, heartbeat_at: datetime) -> None:
        values = {name: getattr(metrics, name) for name in PERSISTED_FIELDS}
        values["outcome_counts"] = dict(metrics.outcome_counts)
        values["last_heartbeat_at"] = heartbeat_at
        statement = insert(WorkerStatusModel).values(worker_id=metrics.worker_id, **values)
        await self.session.execute(
            statement.on_conflict_do_update(index_elements=["worker_id"], set_=values)
        )

    async def latest(self, limit: int = 10) -> list[WorkerStatusModel]:
        result = await self.session.execute(
            select(WorkerStatusModel)
            .order_by(desc(WorkerStatusModel.last_heartbeat_at))
            .limit(limit)
        )
        return list(result.scalars().all())

    async def find(self, worker_id: str) -> WorkerStatusModel | None:
        return await self.session.get(WorkerStatusModel, worker_id)
