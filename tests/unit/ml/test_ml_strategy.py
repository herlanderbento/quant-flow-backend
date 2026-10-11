from datetime import timedelta

import pytest

from ml.features.pipeline import FEATURE_NAMES, FEATURE_SCHEMA_VERSION, WARMUP_CANDLES
from ml.inference.strategy import MLSignalStrategy
from ml.models.artifact import ARTIFACT_FORMAT, ModelPredictor, canonical_sha256
from tests.unit.ml.test_features_and_labels import random_walk
from trader.application.backtest_engine import BacktestCosts, OhlcvCandle, run_backtest
from trader.domain.interface.strategy_interface import MarketData, TradeSignal


def predictor_with_intercept(intercept: float, buy=0.6, sell=0.4, approved=True) -> ModelPredictor:
    n = len(FEATURE_NAMES)
    document = {
        "format": ARTIFACT_FORMAT, "kind": "logistic_regression", "model_version": "const",
        "feature_schema_version": FEATURE_SCHEMA_VERSION, "feature_names": FEATURE_NAMES,
        "params": {"mean": [0.0] * n, "scale": [1.0] * n, "coef": [0.0] * n, "intercept": intercept},
        "decision": {"buy_threshold": buy, "sell_threshold": sell},
    }
    if approved:
        document["approval"] = {"approved_for_trading": True, "approved_by": "test",
                                "reason": "unit test fixture"}
    document["sha256"] = canonical_sha256(document)
    return ModelPredictor(document, FEATURE_SCHEMA_VERSION, FEATURE_NAMES)


def market(frame, rows=None):
    candles = frame.tail(rows or WARMUP_CANDLES)
    as_rows = [[ts.value // 1_000_000, o, h, lo, c, v] for ts, o, h, lo, c, v in candles.itertuples(index=False)]
    closed_at = (candles["timestamp"].iloc[-1] + timedelta(hours=1)).to_pydatetime()
    return MarketData("BTC/USDT", float(candles["close"].iloc[-1]), {}, closed_at, as_rows)


@pytest.mark.parametrize("intercept, expected", [(3.0, TradeSignal.BUY), (-3.0, TradeSignal.SELL),
                                                 (0.0, TradeSignal.HOLD)])
async def test_probability_maps_to_signal(intercept, expected):
    strategy = MLSignalStrategy(predictor_with_intercept(intercept))
    assert await strategy.analyze(market(random_walk())) == expected
    decision = strategy.last_decision
    assert decision.model_version == "const"
    assert decision.reason is None
    assert set(decision.features) == set(FEATURE_NAMES)
    assert decision.feature_candle_close is not None


async def test_unavailable_model_never_buys():
    strategy = MLSignalStrategy(None, unavailable_reason="ML disabled")
    assert await strategy.analyze(market(random_walk())) == TradeSignal.HOLD
    assert strategy.last_decision.reason == "ML disabled"


async def test_short_history_or_gap_is_rejected_with_reason():
    strategy = MLSignalStrategy(predictor_with_intercept(5.0))
    assert await strategy.analyze(market(random_walk(), rows=50)) == TradeSignal.HOLD
    assert strategy.last_decision.reason.startswith("rejected")

    gapped = random_walk().drop(index=550).reset_index(drop=True)
    assert await strategy.analyze(market(gapped)) == TradeSignal.HOLD
    assert "gap" in strategy.last_decision.reason


async def test_stale_market_data_is_rejected():
    frame = random_walk()
    stale = market(frame)
    stale.candle_closed_at = stale.candle_closed_at + timedelta(hours=6)
    strategy = MLSignalStrategy(predictor_with_intercept(5.0))
    assert await strategy.analyze(stale) == TradeSignal.HOLD
    assert "stale" in strategy.last_decision.reason


async def test_backtest_feeds_the_ml_strategy_its_candle_window():
    frame = random_walk(400)
    candles = [OhlcvCandle(r.timestamp.to_pydatetime(), r.open, r.high, r.low, r.close, r.volume)
               for r in frame.itertuples(index=False)]
    strategy = MLSignalStrategy(predictor_with_intercept(5.0))  # always BUY once warm
    metrics = await run_backtest(
        candles=candles, strategy=strategy, symbol="BTC/USDT", allocated_capital=1000,
        stop_loss_pct=50, take_profit_pct=1000, costs=BacktestCosts(0, 0))
    assert metrics.total_trades == 1
    # Never traded before the feature warm-up was available.
    assert metrics.trades[0].entry_time >= candles[WARMUP_CANDLES - 1].timestamp
