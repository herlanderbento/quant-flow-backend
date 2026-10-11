from datetime import datetime, timedelta, timezone
from unittest.mock import AsyncMock, MagicMock

import pytest

from account.domain.credential import CredentialId
from account.domain.user import UserId
from shared.domain.exceptions import ForbiddenException
from trader.application.backtest_engine import BacktestCosts
from trader.application.use_cases.backtest.create_backtest import (
    CreateBacktestInput,
    CreateBacktestUseCase,
)
from trader.domain.bot import Bot

HOUR = timedelta(hours=1)


def _bot(owner):
    return Bot(user_id=UserId(value=owner), credential_id=CredentialId(), name="b",
               symbol="BTC/USDT", strategy_type="RSI_SIMPLE", is_active=False,
               allocated_capital=1000.0, stop_loss_pct=2.0, take_profit_pct=4.0)


def _use_case(bot, rows):
    market = MagicMock()
    market.fetch_ohlcv_history = AsyncMock(return_value=rows)
    market.close = AsyncMock()
    bots = AsyncMock()
    bots.find_by_id.return_value = bot
    users = AsyncMock()
    users.find_by_id.return_value = object()
    results = AsyncMock()
    use_case = CreateBacktestUseCase(
        bots, results, users,
        costs=BacktestCosts(taker_fee_rate=0.001, slippage_bps=5),
        market_data_factory=lambda: market,
    )
    return use_case, market, results


async def test_fetches_warmup_history_ignores_open_candles_and_records_costs():
    owner = UserId().value
    bot = _bot(owner)
    current_open = datetime.now(timezone.utc).replace(minute=0, second=0, microsecond=0)
    end = current_open + HOUR
    start = end - 200 * HOUR
    first = start - 65 * HOUR
    # 266 hourly candles from `first`; the last one opened at `current_open` and is still forming.
    rows = [[int((first + i * HOUR).timestamp() * 1000), 100, 101, 99, 100 + (i % 7), 1]
            for i in range(266)]
    use_case, market, results = _use_case(bot, rows)

    output = await use_case.execute(CreateBacktestInput(
        user_id=UserId(value=owner), bot_id=bot.id, period_start=start, period_end=end))

    since_ms = market.fetch_ohlcv_history.call_args.kwargs["since_ms"]
    assert since_ms == int(first.timestamp() * 1000)
    saved = results.insert.call_args.args[0]
    assert saved.taker_fee_rate == 0.001
    assert saved.slippage_bps == 5
    assert saved.timeframe == "1h"
    assert saved.buy_and_hold_return_pct is not None
    assert all(t.exit_time < current_open for t in output.trades)


async def test_other_users_bot_is_forbidden():
    bot = _bot(UserId().value)
    use_case, _, _ = _use_case(bot, [])
    now = datetime.now(timezone.utc)
    with pytest.raises(ForbiddenException):
        await use_case.execute(CreateBacktestInput(
            user_id=UserId(), bot_id=bot.id, period_start=now - 10 * HOUR, period_end=now))
