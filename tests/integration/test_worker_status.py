from datetime import datetime, timedelta, timezone

import pytest
from httpx import ASGITransport, AsyncClient
from sqlalchemy import update

from main import app
from shared.infra.db.database import get_db_session
from tests.integration.factories import create_bot_setup
from tests.integration.test_worker_recovery import _BuyStrategy, worker_with
from tests.unit.trader.fakes import ScriptedGateway
from trader.infra.db.sql_models import WorkerStatusModel
from trader.infra.db.worker_status_postgres_repository import WorkerStatusPostgresRepository
from trader.infra.worker import bot_worker


@pytest.fixture(autouse=True)
def buy_strategy(monkeypatch):
    monkeypatch.setattr(bot_worker.StrategyFactory, "get_strategy", lambda _: _BuyStrategy())


@pytest.fixture
def api(session_factory):
    async def db_session():
        async with session_factory() as session:
            yield session
            await session.commit()

    app.dependency_overrides[get_db_session] = db_session
    yield AsyncClient(transport=ASGITransport(app=app), base_url="https://test")
    app.dependency_overrides.clear()


async def _status(session_factory, worker_id):
    async with session_factory() as session:
        return await WorkerStatusPostgresRepository(session).find(worker_id)


async def test_cycle_persists_heartbeat_counters_and_market_data_time(session_factory):
    await create_bot_setup(session_factory)
    worker = worker_with(session_factory, ScriptedGateway())
    await worker.run_cycle()
    await worker.run_cycle()

    row = await _status(session_factory, worker.metrics.worker_id)
    assert row.cycles_total == 2
    assert row.cycle_errors_total == 0
    assert row.bots_last_cycle == 1
    assert row.outcome_counts == {"ENTRY_FILLED": 1, "HOLDING": 1}
    assert row.last_market_data_at is not None
    assert row.trading_mode == "paper"


async def test_bot_errors_are_counted_and_consecutive_failures_reset(session_factory):
    await create_bot_setup(session_factory)
    gateway = ScriptedGateway()
    worker = worker_with(session_factory, gateway)

    async def broken(symbol, rsi_period=14):
        raise RuntimeError("Stale market data for BTC/USDT")

    original = gateway.get_market_snapshot
    gateway.get_market_snapshot = broken
    await worker.run_cycle()
    await worker.run_cycle()
    row = await _status(session_factory, worker.metrics.worker_id)
    assert row.consecutive_failures == 2
    assert "Stale market data" in row.last_error

    gateway.get_market_snapshot = original
    await worker.run_cycle()
    row = await _status(session_factory, worker.metrics.worker_id)
    assert row.consecutive_failures == 0
    assert row.cycle_errors_total == 2


async def test_health_reflects_worker_heartbeat(session_factory, api):
    async with api:
        assert (await api.get("/health")).json()["worker"] == "missing"

        worker = worker_with(session_factory, ScriptedGateway())
        await worker.run_cycle()
        response = await api.get("/health")
        assert response.status_code == 200
        assert response.json() == {"status": "ok", "database": "ok", "worker": "ok"}

        async with session_factory() as session:
            await session.execute(update(WorkerStatusModel).values(
                last_heartbeat_at=datetime.now(timezone.utc) - timedelta(minutes=5)))
            await session.commit()
        stale = await api.get("/health")
        assert stale.status_code == 503
        assert stale.json()["worker"] == "stale"


async def test_worker_status_details_require_authentication(api):
    async with api:
        assert (await api.get("/ops/worker-status")).status_code == 401


ALLOWED_WORKER_FIELDS = {
    "worker_id", "state", "trading_mode", "started_at", "last_heartbeat_at",
    "last_cycle_finished_at", "last_market_data_at", "cycles_total", "cycle_errors_total",
    "consecutive_failures", "max_cycle_gap_seconds", "last_audit_at", "audit_ok", "stopped_at",
}


async def test_worker_status_never_returns_other_users_details(session_factory, api):
    other_users_trade = "7d1f0c2e-other-users-trade-id"
    worker = worker_with(session_factory, ScriptedGateway())
    await worker.run_cycle()
    async with session_factory() as session:
        await session.execute(update(WorkerStatusModel).values(
            last_error=f"ValueError: trade {other_users_trade} rejected",
            audit_issues=1,
            audit_details={"issue_count": 1, "issues": [f"trade {other_users_trade} has no fill"]},
            outcome_counts={"POSITION_MISMATCH": 1},
            last_audit_at=datetime.now(timezone.utc),
        ))
        await session.commit()

    async with api:
        email = "observer@quantflow.dev"
        password = "integration-only-password"
        created = await api.post("/users", json={"name": "observer", "email": email, "password": password})
        assert created.status_code == 201, created.text
        assert (await api.post("/auth/login", json={"email": email, "password": password})).status_code == 200

        response = await api.get("/ops/worker-status")

    assert response.status_code == 200
    workers = response.json()["workers"]
    assert len(workers) == 1
    assert set(workers[0]) == ALLOWED_WORKER_FIELDS
    assert workers[0]["state"] == "ok"
    assert workers[0]["audit_ok"] is False
    assert workers[0]["cycles_total"] == 1
    for leaked in (other_users_trade, "POSITION_MISMATCH", "ValueError", "no fill"):
        assert leaked not in response.text


async def test_stopped_worker_is_reported_as_stopped(session_factory, monkeypatch):
    import asyncio
    monkeypatch.setattr(bot_worker, "WORKER_CYCLE_SECONDS", 0.01)
    worker = worker_with(session_factory, ScriptedGateway())
    task = asyncio.create_task(worker.run())
    await asyncio.sleep(0.2)
    worker.stop()
    await asyncio.wait_for(task, timeout=5)
    row = await _status(session_factory, worker.metrics.worker_id)
    assert row.stopped_at is not None
