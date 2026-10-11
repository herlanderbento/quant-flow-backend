from datetime import datetime, timedelta, timezone
from unittest.mock import AsyncMock

import pytest
from sqlalchemy import update

from tests.integration.factories import create_bot_setup
from tests.integration.test_worker_recovery import _BuyStrategy, load_trades, worker_with
from tests.unit.trader.fakes import ScriptedGateway, make_fake_bybit
from trader.application.alerts import AlertService, IAlertSink
from trader.domain.interface.strategy_interface import MarketData
from trader.infra.db.ledger_audit import SimulatedFill, audit_trade_ledger
from trader.infra.db.sql_models import TradeModel
from trader.infra.gateway.bybit_gateway import BybitGateway
from trader.infra.gateway.paper_gateway import PaperExchangeGateway
from trader.infra.worker import bot_worker


@pytest.fixture(autouse=True)
def buy_strategy(monkeypatch):
    monkeypatch.setattr(bot_worker.StrategyFactory, "get_strategy", lambda _: _BuyStrategy())


class RecordingSink(IAlertSink):
    def __init__(self):
        self.keys = []

    async def send(self, key, severity, message, context):
        self.keys.append(key)


def now():
    return datetime.now(timezone.utc)


async def audit(session_factory, **kwargs):
    async with session_factory() as session:
        return await audit_trade_ledger(session, now=now(), stuck_after=timedelta(minutes=10), **kwargs)


async def test_clean_ledger_passes(session_factory):
    _, _, bot = await create_bot_setup(session_factory)
    await worker_with(session_factory, ScriptedGateway())._process_bot(bot)
    gateway = ScriptedGateway(price=40000.0)
    await worker_with(session_factory, gateway)._process_bot(bot)
    assert (await audit(session_factory)).ok


async def test_audit_detects_corrupted_and_stuck_trades(session_factory):
    _, _, bot_a = await create_bot_setup(session_factory)
    _, _, bot_b = await create_bot_setup(session_factory)
    await worker_with(session_factory, ScriptedGateway())._process_bot(bot_a)
    gateway = ScriptedGateway()
    gateway.on_place = lambda *a: (_ for _ in ()).throw(RuntimeError("timeout"))
    await worker_with(session_factory, gateway)._process_bot(bot_b)

    async with session_factory() as session:
        await session.execute(update(TradeModel)
                              .where(TradeModel.bot_config_id == bot_a.id.value)
                              .values(entry_cost=None))
        await session.execute(update(TradeModel)
                              .where(TradeModel.bot_config_id == bot_b.id.value)
                              .values(updated_at=now() - timedelta(hours=1)))
        await session.commit()

    result = await audit(session_factory)
    assert any("invalid entry data" in i for i in result.issues)
    assert any("stuck in PENDING_OPEN" in i for i in result.issues)


async def test_audit_detects_paper_fill_missing_from_ledger(session_factory):
    old = now() - timedelta(minutes=5)
    fills = [SimulatedFill("qf-ghost", "BUY", 0.002, 50000.0, old)]
    result = await audit(session_factory, paper_fills=fills)
    assert result.issues == ["paper fill qf-ghost has no trade"]


async def test_worker_paper_round_trip_matches_simulated_fills(session_factory, monkeypatch):
    """Real PaperExchangeGateway (offline quotes) + real ledger: no divergence."""
    _, _, bot = await create_bot_setup(session_factory)
    exchange = make_fake_bybit()
    exchange.fetch_ticker = AsyncMock(return_value={"bid": 49990.0, "ask": 50010.0, "last": 50000.0})
    paper = PaperExchangeGateway(BybitGateway("", "", exchange=exchange), 0.001, 5)
    price = {"value": 50000.0}
    paper.get_market_snapshot = AsyncMock(side_effect=lambda symbol, rsi_period=14: MarketData(
        symbol=symbol, current_price=price["value"], indicators={}))
    try:
        worker = worker_with(session_factory, paper)
        worker._gateways["paper"] = paper
        await worker._process_bot(bot)  # buy
        price["value"] = 40000.0
        await worker._process_bot(bot)  # stop loss -> sell

        _, closed = await load_trades(session_factory, bot)
        assert closed.status == "CLOSED"
        settled_fills = [
            SimulatedFill(f.client_order_id, f.side, f.filled_quantity, f.average_price, old_time)
            for f, old_time in zip(paper.simulated_fills(), [now() - timedelta(minutes=5)] * 2)
        ]
        assert len(settled_fills) == 2
        result = await audit(session_factory, paper_fills=settled_fills)
        assert result.ok, result.issues
    finally:
        await exchange.close()


async def test_worker_alerts_on_position_mismatch_and_consecutive_failures(session_factory, monkeypatch):
    _, _, bot = await create_bot_setup(session_factory)
    monkeypatch.setattr(bot_worker.settings, "ALERT_CONSECUTIVE_FAILURES", 2)
    sink = RecordingSink()
    gateway = ScriptedGateway()
    worker = worker_with(session_factory, gateway)
    worker.alerts = AlertService([sink])

    await worker.run_cycle()  # opens a position
    gateway.balances = {"BTC": 0.0, "USDT": 0.0}  # position vanished from the account
    await worker.run_cycle()
    assert f"bot.position_mismatch.{bot.id.value}" in sink.keys

    async def broken(symbol, rsi_period=14):
        raise RuntimeError("exchange down")

    gateway.balances = None
    gateway.get_market_snapshot = broken
    await worker.run_cycle()
    await worker.run_cycle()
    assert "worker.consecutive_failures" in sink.keys


async def test_audit_runs_on_schedule_and_is_persisted(session_factory, monkeypatch):
    monkeypatch.setattr(bot_worker.settings, "AUDIT_EVERY_CYCLES", 2)
    await create_bot_setup(session_factory)
    worker = worker_with(session_factory, ScriptedGateway())
    await worker.run_cycle()
    assert worker.metrics.last_audit_at is None
    await worker.run_cycle()
    assert worker.metrics.last_audit_at is not None
    assert worker.metrics.audit_issues == 0
