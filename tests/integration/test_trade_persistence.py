"""Order lifecycle against real PostgreSQL: write-ahead, uniqueness, races, recovery."""
import asyncio
from datetime import datetime, timedelta, timezone

import pytest
from sqlalchemy.exc import IntegrityError

from shared.domain.exceptions import OrderStateUnknownException
from tests.integration.factories import create_bot, create_bot_setup
from tests.unit.trader.fakes import FixedStrategy, ScriptedGateway, filled
from trader.application.bot_cycle import BotCycle, CycleOutcome
from trader.application.risk_guard import RiskGuard, RiskLimits
from trader.domain.interface.strategy_interface import TradeSignal
from trader.domain.trade import (
    TRADE_STATUS_CLOSED,
    TRADE_STATUS_OPEN,
    TRADE_STATUS_PENDING_OPEN,
    Trade,
    TradePendingCommand,
)
from trader.infra.db.bot_postgres_repository import BotPostgresRepository
from trader.infra.db.trade_postgres_repository import TradePostgresRepository

PERMISSIVE = RiskLimits(max_daily_loss_pct=100, max_drawdown_pct=100, max_user_exposure=1e12)


def make_cycle(session, gateway, signal=TradeSignal.BUY, limits=PERMISSIVE, clock=None):
    repo = TradePostgresRepository(session)
    kwargs = {"clock": clock} if clock else {}
    return BotCycle(
        trade_repository=repo,
        gateway=gateway,
        strategy=FixedStrategy(signal),
        risk_guard=RiskGuard(repo, limits),
        commit=session.commit,
        rollback=session.rollback,
        **kwargs, 
    )


async def trades_of(session_factory, bot):
    async with session_factory() as session:
        repo = TradePostgresRepository(session)
        active = await repo.find_active_by_bot_id(bot.id)
        final = await repo.find_latest_final_by_bot_id(bot.id)
    return active, final


async def test_database_rejects_second_active_trade(session_factory):
    _, _, bot = await create_bot_setup(session_factory)

    def pending(cid):
        return Trade.open_pending(TradePendingCommand(
            bot_id=bot.id, symbol="BTC/USDT", side="BUY",
            requested_quantity=0.002, client_order_id=cid))

    async with session_factory() as session:
        await TradePostgresRepository(session).insert(pending("qf-a"))
        await session.commit()

    async with session_factory() as session:
        with pytest.raises(IntegrityError) as error:
            await TradePostgresRepository(session).insert(pending("qf-b"))
            await session.commit()
        assert "uq_trades_one_active_per_bot" in str(error.value)


async def test_duplicate_client_order_id_is_rejected(session_factory):
    user, credential, bot_a = await create_bot_setup(session_factory)
    bot_b = await create_bot(session_factory, user, credential)

    def pending(bot):
        return Trade.open_pending(TradePendingCommand(
            bot_id=bot.id, symbol="BTC/USDT", side="BUY",
            requested_quantity=0.002, client_order_id="qf-same"))

    async with session_factory() as session:
        await TradePostgresRepository(session).insert(pending(bot_a))
        await session.commit()
    async with session_factory() as session:
        with pytest.raises(IntegrityError) as error:
            await TradePostgresRepository(session).insert(pending(bot_b))
            await session.commit()
        assert "uq_trades_client_order_id" in str(error.value)


async def test_missing_entry_context_is_sql_null(session_factory):
    import psycopg2
    from tests.integration.conftest import sync_url

    _, _, bot = await create_bot_setup(session_factory)
    async with session_factory() as session:
        await TradePostgresRepository(session).insert(Trade.open_pending(TradePendingCommand(
            bot_id=bot.id, symbol="BTC/USDT", side="BUY",
            requested_quantity=0.002, client_order_id="qf-ctx")))
        await session.commit()
        database = session.bind.url.database
    with psycopg2.connect(sync_url(database)) as connection, connection.cursor() as cursor:
        cursor.execute("SELECT entry_context IS NULL FROM trades WHERE client_order_id = 'qf-ctx'")
        assert cursor.fetchone()[0] is True
    connection.close()


async def test_pending_trade_is_committed_before_the_order_is_sent(session_factory):
    _, _, bot = await create_bot_setup(session_factory)
    gateway = ScriptedGateway()
    seen_by_another_connection = []

    def on_place(symbol, side, qty, cid):
        # Runs while the cycle waits for the exchange; read through a different connection.
        seen_by_another_connection.append(cid)
        return filled(side, qty, 50000.0, cid)

    async def observe_then_fill(symbol, side, qty, cid):
        active, _ = await trades_of(session_factory, bot)
        seen_by_another_connection.extend(active)
        return on_place(symbol, side, qty, cid)

    gateway.place_market_order = observe_then_fill
    async with session_factory() as session:
        assert await make_cycle(session, gateway).run(bot) == CycleOutcome.ENTRY_FILLED

    committed_trade = seen_by_another_connection[0]
    assert committed_trade.status == TRADE_STATUS_PENDING_OPEN
    assert committed_trade.client_order_id == seen_by_another_connection[1]


@pytest.mark.parametrize("workers", [2, 8])
async def test_concurrent_cycles_open_exactly_one_trade(session_factory, workers):
    _, _, bot = await create_bot_setup(session_factory)
    gateway = ScriptedGateway()
    arrived = 0
    everyone_read = asyncio.Event()
    original_snapshot = gateway.get_market_snapshot

    async def snapshot_after_all_have_read(symbol, rsi_period=14):
        # Every cycle has already queried "no active trade" before anyone inserts.
        nonlocal arrived
        arrived += 1
        if arrived == workers:
            everyone_read.set()
        await everyone_read.wait()
        return await original_snapshot(symbol, rsi_period)

    gateway.get_market_snapshot = snapshot_after_all_have_read

    async def one_worker():
        async with session_factory() as session:
            return await make_cycle(session, gateway).run(bot)

    outcomes = await asyncio.gather(*[one_worker() for _ in range(workers)])

    assert outcomes.count(CycleOutcome.ENTRY_FILLED) == 1
    assert outcomes.count(CycleOutcome.ENTRY_NOT_RECORDED) == workers - 1
    assert len(gateway.sent) == 1
    active, _ = await trades_of(session_factory, bot)
    assert len(active) == 1


async def test_unknown_order_survives_restart_and_is_reconciled(session_factory):
    _, _, bot = await create_bot_setup(session_factory)

    first_process = ScriptedGateway()
    first_process.on_place = lambda *a: (_ for _ in ()).throw(OrderStateUnknownException("timeout"))
    async with session_factory() as session:
        assert await make_cycle(session, first_process).run(bot) == CycleOutcome.ENTRY_PENDING
    cid = first_process.sent[0][2]

    # "Restart": brand-new session and gateway; the exchange did fill the order.
    second_process = ScriptedGateway()
    second_process.lookup[cid] = filled("BUY", 0.002, 50100.0, cid)
    async with session_factory() as session:
        assert await make_cycle(session, second_process).run(bot) == CycleOutcome.ENTRY_FILLED
    assert second_process.sent == []  # reconciled, never re-sent

    active, _ = await trades_of(session_factory, bot)
    assert active[0].status == TRADE_STATUS_OPEN
    assert active[0].price_executed == 50100.0


async def test_unknown_order_never_found_is_cancelled_after_grace(session_factory):
    _, _, bot = await create_bot_setup(session_factory)
    gateway = ScriptedGateway()
    gateway.on_place = lambda *a: (_ for _ in ()).throw(OrderStateUnknownException("lost"))
    async with session_factory() as session:
        await make_cycle(session, gateway).run(bot)

    later = lambda: datetime.now(timezone.utc) + timedelta(minutes=6)  # noqa: E731
    async with session_factory() as session:
        outcome = await make_cycle(session, ScriptedGateway(), clock=later).run(bot)
    assert outcome == CycleOutcome.ENTRY_CANCELLED
    active, final = await trades_of(session_factory, bot)
    assert active == []
    assert final.exit_reason == "NOT_FOUND_ON_EXCHANGE"


async def test_failed_transaction_leaves_no_partial_write(session_factory):
    _, _, bot = await create_bot_setup(session_factory)
    async with session_factory() as session:
        await make_cycle(session, ScriptedGateway()).run(bot)  # OPEN position

    async with session_factory() as session:
        repo = TradePostgresRepository(session)
        [trade] = await repo.find_active_by_bot_id(bot.id)
        trade.start_exit(client_order_id="qf-exit", reason="STOP_LOSS")
        await repo.update(trade)
        await session.flush()
        await session.rollback()  # e.g. crash before commit

    active, _ = await trades_of(session_factory, bot)
    assert active[0].status == TRADE_STATUS_OPEN
    assert active[0].exit_client_order_id is None


async def test_full_round_trip_persists_pnl_fees_and_context(session_factory):
    _, _, bot = await create_bot_setup(session_factory)
    gateway = ScriptedGateway()
    gateway.candle_closed_at = datetime(2026, 1, 1, 12, tzinfo=timezone.utc)
    gateway.on_place = lambda s, side, q, cid: filled(
        side, q, gateway.price, cid,
        fee_cost=q * 0.001 if side == "BUY" else q * gateway.price * 0.001,
        fee_currency="BTC" if side == "BUY" else "USDT")
    async with session_factory() as session:
        await make_cycle(session, gateway).run(bot)
    gateway.price = 48000.0
    async with session_factory() as session:
        assert await make_cycle(session, gateway).run(bot) == CycleOutcome.EXIT_FILLED

    _, closed = await trades_of(session_factory, bot)
    assert closed.status == TRADE_STATUS_CLOSED
    assert closed.exit_reason == "STOP_LOSS"
    assert closed.fee_paid > 0
    assert closed.pnl_usd < 0
    assert closed.entry_context["candle_closed_at"] == "2026-01-01T12:00:00+00:00"
    assert closed.entry_context["strategy"] == "FIXED"


async def test_risk_queries_use_real_sql(session_factory):
    user, credential, bot = await create_bot_setup(session_factory)
    other_bot = await create_bot(session_factory, user, credential, allocated_capital=250.0)
    gateway = ScriptedGateway()
    async with session_factory() as session:
        await make_cycle(session, gateway).run(bot)  # opens: cost basis 100
    gateway.price = 45000.0
    async with session_factory() as session:
        await make_cycle(session, gateway).run(bot)  # closes at a loss
    gateway.price = 50000.0
    gateway.on_place = lambda *a: (_ for _ in ()).throw(OrderStateUnknownException("?"))
    async with session_factory() as session:
        await make_cycle(session, gateway).run(other_bot)  # pending, no cost basis yet

    async with session_factory() as session:
        repo = TradePostgresRepository(session)
        pnls = await repo.realized_pnls(bot.id)
        exposure = await repo.active_exposure_by_user(user.id)
    assert len(pnls) == 1
    assert pnls[0][1] == pytest.approx(0.002 * 45000.0 - 100.0)
    assert exposure == pytest.approx(250.0)  # pending trade counts at the bot's capital


async def test_bot_queries_for_worker_and_halt(session_factory):
    user, credential, active_bot = await create_bot_setup(session_factory)
    idle_bot = await create_bot(session_factory, user, credential, is_active=False)
    winding_down = await create_bot(session_factory, user, credential, is_active=True)
    async with session_factory() as session:
        await make_cycle(session, ScriptedGateway()).run(winding_down)
    async with session_factory() as session:
        repo = BotPostgresRepository(session)
        bot = await repo.find_by_id(winding_down.id)
        bot.deactivate()
        await repo.update(bot)
        await session.commit()

    async with session_factory() as session:
        repo = BotPostgresRepository(session)
        needing = {b.id for b in await repo.find_needing_processing()}
        active_by_user = {b.id for b in await repo.find_active_by_user(user.id)}

    assert needing == {active_bot.id, winding_down.id}
    assert idle_bot.id not in needing
    assert active_by_user == {active_bot.id}


async def test_other_users_bots_are_not_mixed(session_factory):
    user_a, _, bot_a = await create_bot_setup(session_factory)
    user_b, _, _ = await create_bot_setup(session_factory)
    async with session_factory() as session:
        await make_cycle(session, ScriptedGateway()).run(bot_a)
    async with session_factory() as session:
        repo = TradePostgresRepository(session)
        assert await repo.active_exposure_by_user(user_b.id) == 0.0
        assert await repo.active_exposure_by_user(user_a.id) == pytest.approx(100.0)


async def test_balance_check_covers_every_bot_on_the_same_account(session_factory):
    user, credential, bot_a = await create_bot_setup(session_factory)
    bot_b = await create_bot(session_factory, user, credential)
    gateway = ScriptedGateway()
    for bot in (bot_a, bot_b):
        async with session_factory() as session:
            assert await make_cycle(session, gateway).run(bot) == CycleOutcome.ENTRY_FILLED

    # The account only holds the coins of one of the two positions.
    gateway.balances = {"BTC": 0.002, "USDT": 0.0}
    async with session_factory() as session:
        outcome = await make_cycle(session, gateway).run(bot_a)
    assert outcome == CycleOutcome.POSITION_MISMATCH

    gateway.balances = {"BTC": 0.004, "USDT": 0.0}
    async with session_factory() as session:
        assert await make_cycle(session, gateway).run(bot_a) == CycleOutcome.HOLDING
