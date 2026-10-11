"""Values read from Postgres arrive as Decimal; calculations must not break on them."""
from datetime import datetime, timedelta, timezone
from decimal import Decimal

import pytest

from trader.application.backtest_engine import OhlcvCandle, run_backtest
from trader.application.order_sizing import calculate_order_quantity
from trader.domain.strategies.simple_rsi_strategy import SimpleRsiStrategy


def test_order_sizing_accepts_decimal():
    assert calculate_order_quantity(Decimal("100"), 50000.0) == pytest.approx(0.002)


async def test_backtest_accepts_decimal_parameters():
    start = datetime(2026, 1, 1, tzinfo=timezone.utc)
    closes = [100 - i for i in range(20)] + [80 + i for i in range(20)]
    candles = [
        OhlcvCandle(start + timedelta(hours=i), c, c, c, c, 1.0)
        for i, c in enumerate(closes)
    ]
    metrics = await run_backtest(
        candles=candles,
        strategy=SimpleRsiStrategy(),
        symbol="BTC/USDT",
        allocated_capital=Decimal("1000"),
        stop_loss_pct=Decimal("2.00"),
        take_profit_pct=Decimal("4.00"),
    )
    assert isinstance(metrics.total_return_pct, float)
    assert metrics.total_trades >= 1
