"""ML in the worker against PostgreSQL: shadow never changes decisions; gating holds."""
from datetime import timedelta

import pytest
from sqlalchemy import select

from ml.inference.strategy import ML_STRATEGY_NAME
from tests.integration.factories import create_bot_setup
from tests.integration.test_worker_recovery import _BuyStrategy, load_trades, worker_with
from tests.unit.ml.test_features_and_labels import random_walk
from tests.unit.ml.test_ml_strategy import predictor_with_intercept
from tests.unit.trader.fakes import ScriptedGateway
from trader.domain.interface.strategy_interface import MarketData
from trader.infra.db.sql_models import AIPredictionModel
from trader.infra.worker import bot_worker


class CandleGateway(ScriptedGateway):
    """Scripted exchange that also serves real-looking closed candles."""

    def __init__(self, price=50000.0):
        super().__init__(price)
        frame = random_walk(300)
        self.rows = [[ts.value // 1_000_000, o, h, lo, c, v]
                     for ts, o, h, lo, c, v in frame.itertuples(index=False)]
        self.candle_closed_at = (frame["timestamp"].iloc[-1] + timedelta(hours=1)).to_pydatetime()

    async def get_market_snapshot(self, symbol, rsi_period=14):
        return MarketData(symbol, self.price, {}, self.candle_closed_at, self.rows)


class ExplodingStrategy:
    """A shadow model that crashes must not affect the real strategy."""
    required_candles = 0

    def decide(self, market_data):
        raise RuntimeError("model blew up")


@pytest.fixture(autouse=True)
def rsi_bots_buy(monkeypatch):
    monkeypatch.setattr(bot_worker.StrategyFactory, "get_strategy", lambda _: _BuyStrategy())


def settings_with(monkeypatch, **values):
    for key, value in values.items():
        monkeypatch.setattr(bot_worker.settings, key, value)


async def predictions(session_factory):
    async with session_factory() as session:
        return (await session.execute(select(AIPredictionModel))).scalars().all()


async def test_shadow_records_once_per_candle_and_never_changes_the_decision(session_factory, monkeypatch):
    settings_with(monkeypatch, ML_SHADOW_ENABLED=True)
    _, _, bot = await create_bot_setup(session_factory)
    worker = worker_with(session_factory, CandleGateway())
    worker.predictor = predictor_with_intercept(-5.0)  # model strongly says SELL

    await worker._process_bot(bot)   # real strategy says BUY -> position opened
    await worker._process_bot(bot)   # same candle -> no second record

    active, _ = await load_trades(session_factory, bot)
    assert active[0].status == "OPEN"
    [row] = await predictions(session_factory)
    assert row.mode == "shadow"
    assert row.decision == "SELL"
    assert row.strategy_signal == "BUY"
    assert float(row.probability) < 0.01
    assert row.feature_candle_close is not None
    assert row.ai_model_version == "const"


async def test_crashing_shadow_model_does_not_affect_trading(session_factory, monkeypatch):
    settings_with(monkeypatch, ML_SHADOW_ENABLED=True)
    _, _, bot = await create_bot_setup(session_factory)
    worker = worker_with(session_factory, CandleGateway())
    worker.predictor = predictor_with_intercept(0.0)
    original = worker._strategy_for

    def strategy_with_exploding_shadow(b):
        strategy = original(b)
        strategy.shadow = ExplodingStrategy()
        return strategy

    worker._strategy_for = strategy_with_exploding_shadow
    await worker._process_bot(bot)
    active, _ = await load_trades(session_factory, bot)
    assert active[0].status == "OPEN"
    assert await predictions(session_factory) == []


async def test_ml_bot_does_not_trade_unless_explicitly_enabled(session_factory, monkeypatch):
    settings_with(monkeypatch, ML_TRADING_ENABLED=False)
    _, _, bot = await create_bot_setup(session_factory, strategy_type=ML_STRATEGY_NAME)
    gateway = CandleGateway()
    worker = worker_with(session_factory, gateway)
    worker.predictor = predictor_with_intercept(5.0)  # would BUY

    await worker._process_bot(bot)
    assert gateway.sent == []
    assert worker.metrics.outcome_counts == {"NO_SIGNAL": 1}


async def test_ml_bot_never_gets_the_model_in_live_mode(session_factory, monkeypatch):
    settings_with(monkeypatch, ML_TRADING_ENABLED=True, TRADING_MODE="live", LIVE_TRADING_ENABLED=True)
    _, _, bot = await create_bot_setup(session_factory, strategy_type=ML_STRATEGY_NAME)
    gateway = CandleGateway()
    worker = worker_with(session_factory, gateway)
    worker.predictor = predictor_with_intercept(5.0)

    strategy = worker._strategy_for(bot)
    assert strategy.predictor is None
    assert "live" in strategy.unavailable_reason
    await worker._process_bot(bot)
    assert gateway.sent == []


async def test_enabled_ml_bot_trades_through_the_normal_cycle_and_logs(session_factory, monkeypatch):
    settings_with(monkeypatch, ML_TRADING_ENABLED=True, TRADING_MODE="paper")
    _, _, bot = await create_bot_setup(session_factory, strategy_type=ML_STRATEGY_NAME)
    gateway = CandleGateway()
    worker = worker_with(session_factory, gateway)
    worker.predictor = predictor_with_intercept(5.0)

    await worker._process_bot(bot)
    active, _ = await load_trades(session_factory, bot)
    assert active[0].status == "OPEN"
    assert active[0].entry_context["model"]["version"] == "const"
    [row] = await predictions(session_factory)
    assert row.mode == "active"
    assert row.decision == "BUY"


async def test_kill_switch_still_blocks_ml_entries(session_factory, monkeypatch):
    settings_with(monkeypatch, ML_TRADING_ENABLED=True, TRADING_MODE="paper", TRADING_HALTED=True)
    _, _, bot = await create_bot_setup(session_factory, strategy_type=ML_STRATEGY_NAME)
    gateway = CandleGateway()
    worker = worker_with(session_factory, gateway)
    worker.predictor = predictor_with_intercept(5.0)

    await worker._process_bot(bot)
    assert gateway.sent == []
    assert worker.metrics.outcome_counts == {"RISK_BLOCKED": 1}


async def test_ml_position_still_exits_on_stop_loss_when_ml_is_switched_off(session_factory, monkeypatch):
    settings_with(monkeypatch, ML_TRADING_ENABLED=True, TRADING_MODE="paper")
    _, _, bot = await create_bot_setup(session_factory, strategy_type=ML_STRATEGY_NAME)
    gateway = CandleGateway()
    worker = worker_with(session_factory, gateway)
    worker.predictor = predictor_with_intercept(5.0)
    await worker._process_bot(bot)

    settings_with(monkeypatch, ML_TRADING_ENABLED=False)
    gateway.price = 40000.0
    await worker._process_bot(bot)
    _, closed = await load_trades(session_factory, bot)
    assert closed.status == "CLOSED"
    assert closed.exit_reason == "STOP_LOSS"


async def test_unapproved_model_only_runs_in_shadow(session_factory, monkeypatch):
    settings_with(monkeypatch, ML_TRADING_ENABLED=True, TRADING_MODE="paper")
    _, _, bot = await create_bot_setup(session_factory, strategy_type=ML_STRATEGY_NAME)
    gateway = CandleGateway()
    worker = worker_with(session_factory, gateway)
    worker.predictor = predictor_with_intercept(5.0, approved=False)

    strategy = worker._strategy_for(bot)
    assert strategy.predictor is None
    assert "not approved" in strategy.unavailable_reason
    await worker._process_bot(bot)
    assert gateway.sent == []
