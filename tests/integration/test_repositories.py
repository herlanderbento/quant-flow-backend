from datetime import date, datetime, timedelta, timezone

import pytest

from account.domain.user import UserId
from shared.domain.search_input import SortDirection
from tests.integration.factories import create_bot_setup
from trader.domain.backtest_result import BacktestCreateCommand, BacktestResult
from trader.domain.repositories.trade_repository import TradeFilter, TradeSearchInput
from trader.infra.db.backtest_postgres_repository import BacktestPostgresRepository
from trader.infra.db.trade_postgres_repository import TradePostgresRepository
from trader.domain.trade import Trade, TradePendingCommand
from wallet.infra.db.wallet_snapshot_postgres_repository import WalletSnapshotPostgresRepository


async def test_backtest_result_roundtrip_with_cost_metrics(session_factory):
    _, _, bot = await create_bot_setup(session_factory)
    now = datetime.now(timezone.utc)
    result = BacktestResult.create(BacktestCreateCommand(
        bot_id=bot.id, strategy_type="RSI_SIMPLE", symbol="BTC/USDT",
        period_start=now - timedelta(days=30), period_end=now,
        total_return_pct=-1.5, sharpe_ratio=-0.4, max_drawdown_pct=-6.2, win_rate=0.42,
        total_trades=31, timeframe="1h", profit_factor=0.87, expectancy_pct=-0.05,
        buy_and_hold_return_pct=3.1, exposure_pct=22.5, fees_paid=6.2,
        taker_fee_rate=0.001, slippage_bps=5.0))
    async with session_factory() as session:
        await BacktestPostgresRepository(session).insert(result)
        await session.commit()
    async with session_factory() as session:
        loaded = await BacktestPostgresRepository(session).find_by_id(result.id)

    assert loaded.profit_factor == pytest.approx(0.87)
    assert loaded.buy_and_hold_return_pct == pytest.approx(3.1)
    assert loaded.taker_fee_rate == pytest.approx(0.001)
    assert loaded.timeframe == "1h"


async def test_trade_search_is_scoped_to_the_owner(session_factory):
    user_a, _, bot_a = await create_bot_setup(session_factory)
    user_b, _, bot_b = await create_bot_setup(session_factory)
    async with session_factory() as session:
        repo = TradePostgresRepository(session)
        for bot, cid in ((bot_a, "qf-a"), (bot_b, "qf-b")):
            await repo.insert(Trade.open_pending(TradePendingCommand(
                bot_id=bot.id, symbol="BTC/USDT", side="BUY",
                requested_quantity=0.002, client_order_id=cid)))
        await session.commit()

    async with session_factory() as session:
        found = await TradePostgresRepository(session).find_by_user_id(
            user_a.id, TradeSearchInput(init_page=1, init_per_page=10,
                                        init_sort_dir=SortDirection.DESC,
                                        init_filter=TradeFilter()))
    assert [t.client_order_id for t in found.items] == ["qf-a"]
    assert found.total == 1


async def test_wallet_snapshot_persists_and_reloads(session_factory):
    user, _, _ = await create_bot_setup(session_factory)
    async with session_factory() as session:
        repo = WalletSnapshotPostgresRepository(session)
        saved = await repo.save_daily_snapshot(UserId(value=user.id.value), 1234.5, date(2026, 1, 2))
        await session.commit()
    async with session_factory() as session:
        again = await WalletSnapshotPostgresRepository(session).save_daily_snapshot(
            UserId(value=user.id.value), 999.0, date(2026, 1, 2))
    assert again.id == saved.id
    assert again.total_equity_usdt == 999.0  # latest value of the day, not the first
