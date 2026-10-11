"""The real BotWorker against PostgreSQL: restarts, winding down, graceful stop."""
import asyncio

import pytest

from shared.domain.exceptions import OrderStateUnknownException
from tests.integration.factories import create_bot_setup
from tests.unit.trader.fakes import ScriptedGateway, filled
from trader.domain.trade import TRADE_STATUS_CLOSED, TRADE_STATUS_OPEN, TRADE_STATUS_PENDING_OPEN
from trader.infra.db.bot_postgres_repository import BotPostgresRepository
from trader.infra.db.trade_postgres_repository import TradePostgresRepository
from trader.infra.worker import bot_worker
from trader.infra.worker.bot_worker import BotWorker


class _BuyStrategy:
    name = "FIXED"

    async def analyze(self, market_data):
        from trader.domain.interface.strategy_interface import TradeSignal
        return TradeSignal.BUY


@pytest.fixture(autouse=True)
def buy_strategy(monkeypatch):
    monkeypatch.setattr(bot_worker.StrategyFactory, "get_strategy", lambda _: _BuyStrategy())


def worker_with(session_factory, gateway) -> BotWorker:
    worker = BotWorker(session_factory, encryption_service=None)

    async def gateway_for(_credential):
        return gateway

    worker._gateway_for = gateway_for
    return worker


async def load_trades(session_factory, bot):
    async with session_factory() as session:
        repo = TradePostgresRepository(session)
        return await repo.find_active_by_bot_id(bot.id), await repo.find_latest_final_by_bot_id(bot.id)


async def test_new_worker_process_recovers_pending_entry(session_factory):
    _, _, bot = await create_bot_setup(session_factory)
    crashed_gateway = ScriptedGateway()
    crashed_gateway.on_place = lambda *a: (_ for _ in ()).throw(OrderStateUnknownException("timeout"))
    await worker_with(session_factory, crashed_gateway)._process_bot(bot)
    active, _ = await load_trades(session_factory, bot)
    assert active[0].status == TRADE_STATUS_PENDING_OPEN

    cid = crashed_gateway.sent[0][2]
    restarted_gateway = ScriptedGateway()
    restarted_gateway.lookup[cid] = filled("BUY", 0.002, 50000.0, cid)
    await worker_with(session_factory, restarted_gateway)._process_bot(bot)

    active, _ = await load_trades(session_factory, bot)
    assert active[0].status == TRADE_STATUS_OPEN
    assert restarted_gateway.sent == []


async def test_restarted_worker_protects_position_of_deactivated_bot(session_factory):
    _, _, bot = await create_bot_setup(session_factory)
    gateway = ScriptedGateway()
    await worker_with(session_factory, gateway)._process_bot(bot)

    async with session_factory() as session:
        repo = BotPostgresRepository(session)
        stored = await repo.find_by_id(bot.id)
        stored.deactivate()
        await repo.update(stored)
        await session.commit()

    # A fresh worker discovers the bot through find_needing_processing, as run() does.
    restarted = ScriptedGateway(price=40000.0)
    worker = worker_with(session_factory, restarted)
    async with session_factory() as session:
        bots = await BotPostgresRepository(session).find_needing_processing()
    assert [b.id for b in bots] == [bot.id]
    await worker._process_bot(bots[0])

    active, closed = await load_trades(session_factory, bot)
    assert active == []
    assert closed.status == TRADE_STATUS_CLOSED
    assert [s[0] for s in restarted.sent] == ["SELL"]


async def test_run_loop_survives_errors_and_stops_gracefully(session_factory, monkeypatch):
    _, _, bot = await create_bot_setup(session_factory)
    monkeypatch.setattr(bot_worker, "WORKER_CYCLE_SECONDS", 0.01)
    gateway = ScriptedGateway()
    calls = 0
    original = gateway.get_market_snapshot

    async def flaky_snapshot(symbol, rsi_period=14):
        nonlocal calls
        calls += 1
        if calls == 1:
            raise RuntimeError("exchange hiccup")
        return await original(symbol, rsi_period)

    gateway.get_market_snapshot = flaky_snapshot
    worker = worker_with(session_factory, gateway)
    closed_gateways = []

    async def close_gateways():
        closed_gateways.append(True)

    worker.close_gateways = close_gateways

    task = asyncio.create_task(worker.run())
    for _ in range(300):
        active, _ = await load_trades(session_factory, bot)
        if active and active[0].status == TRADE_STATUS_OPEN:
            break
        await asyncio.sleep(0.02)
    worker.stop()
    await asyncio.wait_for(task, timeout=5)

    assert calls >= 2  # the failing cycle did not kill the loop
    assert active and active[0].status == TRADE_STATUS_OPEN
    assert closed_gateways == [True]


async def test_stop_interrupts_the_wait_between_cycles(session_factory, monkeypatch):
    monkeypatch.setattr(bot_worker, "WORKER_CYCLE_SECONDS", 60)
    worker = worker_with(session_factory, ScriptedGateway())
    task = asyncio.create_task(worker.run())
    await asyncio.sleep(0.3)  # first cycle done, now waiting 60 s
    worker.stop()
    await asyncio.wait_for(task, timeout=3)  # returns long before 60 s


async def test_cycles_recover_after_database_connections_are_killed(session_factory):
    import psycopg2
    from tests.integration.conftest import ADMIN_URL

    _, _, bot = await create_bot_setup(session_factory)
    worker = worker_with(session_factory, ScriptedGateway())
    await worker._process_bot(bot)  # warms the pool

    # Simulate a database restart: every server connection to this database is dropped.
    database = session_factory.kw["bind"].url.database
    connection = psycopg2.connect(ADMIN_URL)
    connection.autocommit = True
    with connection.cursor() as cursor:
        cursor.execute("SELECT pg_terminate_backend(pid) FROM pg_stat_activity "
                       "WHERE datname = %s AND pid <> pg_backend_pid()", (database,))
    connection.close()

    gateway = ScriptedGateway(price=40000.0)
    worker = worker_with(session_factory, gateway)
    await worker._process_bot(bot)  # must reconnect and close the position
    active, closed = await load_trades(session_factory, bot)
    assert active == []
    assert closed.status == TRADE_STATUS_CLOSED
