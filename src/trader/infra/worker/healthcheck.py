"""Container healthcheck: exit 0 if this host's worker wrote a fresh heartbeat.

    python -m trader.infra.worker.healthcheck
"""
import asyncio
import socket
import sys
from datetime import datetime, timezone

from sqlalchemy import desc, select

from shared.infra.db.config import settings
from shared.infra.db.database import AsyncSessionLocal, engine
import shared.infra.db.metadata  # noqa: F401  registers every ORM model
from trader.infra.db.sql_models import WorkerStatusModel


async def heartbeat_age_seconds(hostname: str) -> float | None:
    async with AsyncSessionLocal() as session:
        result = await session.execute(
            select(WorkerStatusModel.last_heartbeat_at)
            .where(WorkerStatusModel.hostname == hostname, WorkerStatusModel.stopped_at.is_(None))
            .order_by(desc(WorkerStatusModel.last_heartbeat_at))
            .limit(1)
        )
        last = result.scalar_one_or_none()
    await engine.dispose()
    if last is None:
        return None
    return (datetime.now(timezone.utc) - last).total_seconds()


def main() -> int:
    try:
        age = asyncio.run(heartbeat_age_seconds(socket.gethostname()))
    except Exception as error:
        print(f"unhealthy: database unavailable ({type(error).__name__})")
        return 1
    if age is None or age > settings.WORKER_STALE_SECONDS:
        print(f"unhealthy: heartbeat age {age}")
        return 1
    print(f"healthy: heartbeat age {age:.1f}s")
    return 0


if __name__ == "__main__":
    sys.exit(main())
