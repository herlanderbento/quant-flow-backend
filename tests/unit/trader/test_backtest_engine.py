from datetime import datetime, timedelta, timezone

import pytest

from trader.application.backtest_engine import BacktestCosts, OhlcvCandle, run_backtest
from trader.domain.interface.strategy_interface import IBotStrategy, TradeSignal

T0 = datetime(2026, 1, 1, tzinfo=timezone.utc)
NO_COSTS = BacktestCosts(taker_fee_rate=0.0, slippage_bps=0.0)


class ScriptedStrategy(IBotStrategy):
    """Returns signals[i] on the i-th closed trading candle."""

    def __init__(self, signals):
        self.signals = list(signals)
        self.calls = 0

    @property
    def name(self):
        return "SCRIPTED"

    async def analyze(self, market_data):
        signal = self.signals[self.calls] if self.calls < len(self.signals) else TradeSignal.HOLD
        self.calls += 1
        return signal


B, S, H = TradeSignal.BUY, TradeSignal.SELL, TradeSignal.HOLD


def candle(i, o, h=None, lo=None, c=None):
    c = o if c is None else c
    return OhlcvCandle(T0 + timedelta(hours=i), o, h or max(o, c), lo or min(o, c), c, 1.0)


async def run(candles, signals, costs=NO_COSTS, sl=50.0, tp=1000.0, **kw):
    return await run_backtest(
        candles=candles, strategy=ScriptedStrategy(signals), symbol="BTC/USDT",
        allocated_capital=1000.0, stop_loss_pct=sl, take_profit_pct=tp, costs=costs, **kw,
    )


async def test_signal_on_close_fills_at_next_open_not_same_close():
    # BUY decided at close of candle 0 (100); candle 1 opens at 110.
    candles = [candle(0, 100), candle(1, 110, c=120), candle(2, 120)]
    m = await run(candles, [B, H, H])
    [t] = m.trades
    assert t.entry_price == 110.0
    assert t.exit_reason == "END_OF_DATA"


async def test_sell_signal_exits_at_next_open():
    candles = [candle(0, 100), candle(1, 100), candle(2, 100, c=130), candle(3, 125), candle(4, 90)]
    m = await run(candles, [B, H, S, H])
    [t] = m.trades
    assert t.exit_reason == "SIGNAL"
    assert t.exit_price == 125.0
    assert t.pnl == pytest.approx(1000 * 125 / 100 - 1000)


async def test_round_trip_on_flat_market_costs_fees_and_slippage():
    costs = BacktestCosts(taker_fee_rate=0.001, slippage_bps=10)
    candles = [candle(i, 100) for i in range(4)]
    m = await run(candles, [B, S], costs=costs)
    [t] = m.trades
    held = (1000 / 100.1) * 0.999
    expected_equity = held * 99.9 * 0.999
    assert t.exit_reason == "SIGNAL"
    assert t.pnl == pytest.approx(expected_equity - 1000)
    assert m.total_return_pct == pytest.approx((expected_equity - 1000) / 10, abs=1e-4)
    assert m.fees_paid == pytest.approx((1000 / 100.1) * 0.001 * 100.1 + held * 99.9 * 0.001)


async def test_intrabar_stop_is_hit_even_if_candle_closes_higher():
    candles = [candle(0, 100), candle(1, 100), candle(2, 100, h=101, lo=80, c=100)]
    m = await run(candles, [B, H, H], sl=5.0)
    [t] = m.trades
    assert t.exit_reason == "STOP_LOSS"
    assert t.exit_price == pytest.approx(95.0)


async def test_stop_wins_when_stop_and_target_touch_same_candle():
    candles = [candle(0, 100), candle(1, 100), candle(2, 100, h=120, lo=90, c=100)]
    m = await run(candles, [B, H, H], sl=5.0, tp=10.0)
    assert m.trades[0].exit_reason == "STOP_LOSS"


async def test_gap_below_stop_fills_at_open():
    candles = [candle(0, 100), candle(1, 100), candle(2, 70, c=72)]
    m = await run(candles, [B, H, H], sl=5.0)
    assert m.trades[0].exit_price == 70.0


async def test_take_profit_fills_at_target():
    candles = [candle(0, 100), candle(1, 100), candle(2, 100, h=130, lo=99, c=101)]
    m = await run(candles, [B, H, H], tp=10.0)
    assert m.trades[0].exit_reason == "TAKE_PROFIT"
    assert m.trades[0].exit_price == pytest.approx(110.0)


async def test_warmup_candles_never_trade():
    candles = [candle(i, 100 + i) for i in range(10)]
    m = await run(candles, [B] * 10, trade_start=T0 + timedelta(hours=8))
    # Signals only on candles 8 and 9: entry at 9's open, closed at end of data.
    assert [t.entry_time for t in m.trades] == [T0 + timedelta(hours=9)]


async def test_metrics_profit_factor_expectancy_and_buy_and_hold():
    # Trade 1: 100 -> 120 (+20%), trade 2: 120 -> 108 (-10%)
    candles = [candle(0, 100), candle(1, 100), candle(2, 120), candle(3, 120), candle(4, 120),
               candle(5, 108), candle(6, 108)]
    m = await run(candles, [B, S, H, B, S, H])
    assert m.total_trades == 2
    win, loss = m.trades
    assert win.pnl == pytest.approx(200.0)
    assert loss.pnl == pytest.approx(-120.0)
    assert m.profit_factor == pytest.approx(200 / 120, abs=1e-4)
    assert m.expectancy_pct == pytest.approx((20 - 10) / 2)
    assert m.win_rate == 0.5
    assert m.buy_and_hold_return_pct == pytest.approx(8.0)
    assert m.total_return_pct == pytest.approx(8.0)


async def test_drawdown_is_mark_to_market():
    candles = [candle(0, 100), candle(1, 100), candle(2, 60), candle(3, 100)]
    m = await run(candles, [B, H, H])
    assert m.max_drawdown_pct == pytest.approx(-40.0)
