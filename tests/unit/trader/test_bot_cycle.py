import copy
from datetime import datetime, timedelta, timezone
from unittest.mock import AsyncMock

import pytest

from shared.domain.exceptions import (
    GatewayException,
    OrderRejectedException,
    OrderStateUnknownException,
)
from tests.unit.trader.fakes import FixedStrategy, ScriptedGateway, filled, make_fake_bybit
from trader.application.bot_cycle import BotCycle, CycleOutcome
from trader.application.risk_guard import RiskGuard, RiskLimits
from trader.domain.bot import Bot, BotId
from trader.domain.interface.exchange_gateway_interface import TradingRules
from trader.domain.interface.strategy_interface import (
    IBotStrategy,
    MarketData,
    TradeSignal,
)
from trader.domain.trade import (
    ACTIVE_TRADE_STATUSES,
    TRADE_STATUS_CANCELLED,
    TRADE_STATUS_CLOSED,
    TRADE_STATUS_OPEN,
    TRADE_STATUS_PENDING_CLOSE,
    TRADE_STATUS_PENDING_OPEN,
    Trade,
)
from trader.infra.gateway.bybit_gateway import BybitGateway
from trader.infra.gateway.paper_gateway import PaperExchangeGateway
from account.domain.credential import CredentialId
from account.domain.user import UserId

SYMBOL = "BTC/USDT"
PERMISSIVE = RiskLimits(max_daily_loss_pct=100, max_drawdown_pct=100, max_user_exposure=1e12)


# ---- doubles -----------------------------------------------------------------


class InMemoryTradeRepository:
    """Session-like store: writes are staged until commit; the unique index is enforced on commit."""

    def __init__(self):
        self.staged: dict = {}
        self.committed: dict = {}
        self.fail_next_commit = False

    async def insert(self, trade: Trade) -> None:
        self.staged[trade.id.value] = copy.deepcopy(trade)

    async def update(self, trade: Trade) -> None:
        self.staged[trade.id.value] = copy.deepcopy(trade)

    async def find_active_by_bot_id(self, bot_id):
        return [
            copy.deepcopy(t)
            for t in self.staged.values()
            if t.bot_id == bot_id and t.status in ACTIVE_TRADE_STATUSES
        ]

    async def find_latest_final_by_bot_id(self, bot_id):
        final = [
            t for t in self.staged.values()
            if t.bot_id == bot_id and not t.is_active and t.closed_at is not None
        ]
        return copy.deepcopy(max(final, key=lambda t: t.closed_at)) if final else None

    async def realized_pnls(self, bot_id):
        closed = sorted(
            (t for t in self.staged.values()
             if t.bot_id == bot_id and t.status == TRADE_STATUS_CLOSED and t.pnl_usd is not None),
            key=lambda t: t.closed_at,
        )
        return [(t.closed_at, t.pnl_usd) for t in closed]

    async def open_base_quantity(self, credential_id, base_asset):
        return sum(
            (t.open_quantity if t.open_quantity is not None else t.quantity)
            for t in self.staged.values()
            if t.symbol.startswith(f"{base_asset}/") and t.status in ("OPEN", "PENDING_CLOSE")
        )

    async def active_exposure_by_user(self, user_id):
        return 0.0  # single-bot tests; exposure is covered in test_risk_guard

    async def commit(self) -> None:
        if self.fail_next_commit:
            self.fail_next_commit = False
            raise RuntimeError("db down")
        per_bot: dict = {}
        for t in self.staged.values():
            if t.status in ACTIVE_TRADE_STATUSES:
                per_bot[t.bot_id.value] = per_bot.get(t.bot_id.value, 0) + 1
        if any(count > 1 for count in per_bot.values()):
            raise RuntimeError("unique violation: uq_trades_one_active_per_bot")
        self.committed = copy.deepcopy(self.staged)

    async def rollback(self) -> None:
        self.staged = copy.deepcopy(self.committed)

    def committed_trades(self) -> list[Trade]:
        return list(self.committed.values())


class Clock:
    def __init__(self):
        self.now = datetime.now(timezone.utc)

    def __call__(self):
        return self.now


def make_bot(**overrides) -> Bot:
    data = dict(
        id=BotId(),
        user_id=UserId(),
        credential_id=CredentialId(),
        name="bot",
        symbol=SYMBOL,
        strategy_type="RSI_SIMPLE",
        is_active=True,
        allocated_capital=100.0,
        stop_loss_pct=2.0,
        take_profit_pct=4.0,
    )
    data.update(overrides)
    return Bot(**data)


@pytest.fixture
def env():
    repo = InMemoryTradeRepository()
    gateway = ScriptedGateway()
    clock = Clock()

    def cycle(signal=TradeSignal.BUY, gw=None):
        return BotCycle(
            trade_repository=repo,
            gateway=gw or gateway,
            strategy=FixedStrategy(signal),
            risk_guard=RiskGuard(repo, PERMISSIVE),
            commit=repo.commit,
            rollback=repo.rollback,
            clock=clock,
            pending_grace=timedelta(minutes=5),
        )

    return repo, gateway, clock, cycle


# ---- entry -------------------------------------------------------------------


async def test_pending_trade_is_committed_before_order_is_sent(env):
    repo, gateway, _, cycle = env
    seen_at_send = []

    def on_place(symbol, side, qty, cid):
        seen_at_send.extend(repo.committed_trades())
        return filled(side, qty, 50000.0, cid, fee_cost=qty * 0.001, fee_currency="BTC")

    gateway.on_place = on_place
    outcome = await cycle().run(make_bot())

    assert outcome == CycleOutcome.ENTRY_FILLED
    assert len(seen_at_send) == 1
    assert seen_at_send[0].status == TRADE_STATUS_PENDING_OPEN
    assert seen_at_send[0].client_order_id == gateway.sent[0][2]

    [trade] = repo.committed_trades()
    assert trade.status == TRADE_STATUS_OPEN
    assert trade.quantity == pytest.approx(0.002 * 0.999)  # net of base-asset fee
    assert trade.entry_cost == pytest.approx(100.0)
    assert trade.fee_paid == pytest.approx(0.002 * 0.001 * 50000.0)


async def test_unknown_entry_is_never_resent_and_gets_reconciled(env):
    repo, gateway, _, cycle = env
    bot = make_bot()

    def unknown(symbol, side, qty, cid):
        raise OrderStateUnknownException("timeout")

    gateway.on_place = unknown
    assert await cycle().run(bot) == CycleOutcome.ENTRY_PENDING

    # Signal still says BUY on the next cycles, but the order must not be re-sent.
    for _ in range(5):
        assert await cycle().run(bot) == CycleOutcome.ENTRY_PENDING
    assert len(gateway.sent) == 1

    cid = gateway.sent[0][2]
    gateway.lookup[cid] = filled("BUY", 0.002, 50100.0, cid)
    assert await cycle().run(bot) == CycleOutcome.ENTRY_FILLED
    assert len(gateway.sent) == 1
    [trade] = repo.committed_trades()
    assert trade.status == TRADE_STATUS_OPEN
    assert trade.price_executed == 50100.0


async def test_unexpected_error_after_send_is_treated_as_unknown(env):
    repo, gateway, _, cycle = env

    def boom(symbol, side, qty, cid):
        raise TypeError("float() argument must be a string or a real number")

    gateway.on_place = boom
    bot = make_bot()
    await cycle().run(bot)
    await cycle().run(bot)
    assert len(gateway.sent) == 1
    assert repo.committed_trades()[0].status == TRADE_STATUS_PENDING_OPEN


async def test_entry_missing_on_exchange_is_cancelled_only_after_grace(env):
    repo, gateway, clock, cycle = env
    gateway.on_place = lambda *a: (_ for _ in ()).throw(OrderStateUnknownException("lost"))
    bot = make_bot()
    await cycle().run(bot)

    clock.now += timedelta(minutes=4)
    assert await cycle().run(bot) == CycleOutcome.ENTRY_PENDING

    clock.now += timedelta(minutes=2)
    assert await cycle().run(bot) == CycleOutcome.ENTRY_CANCELLED
    assert repo.committed_trades()[0].status == TRADE_STATUS_CANCELLED

    # Only now may a new entry be attempted.
    gateway.on_place = None
    assert await cycle().run(bot) == CycleOutcome.ENTRY_FILLED
    assert len(gateway.sent) == 2


async def test_reconcile_lookup_failure_keeps_trade_pending(env):
    repo, gateway, clock, cycle = env
    gateway.on_place = lambda *a: (_ for _ in ()).throw(OrderStateUnknownException("lost"))
    bot = make_bot()
    await cycle().run(bot)

    gateway.lookup_error = GatewayException("api down")
    clock.now += timedelta(hours=1)
    assert await cycle().run(bot) == CycleOutcome.RECONCILE_FAILED
    assert repo.committed_trades()[0].status == TRADE_STATUS_PENDING_OPEN


async def test_rejected_entry_is_cancelled(env):
    repo, gateway, _, cycle = env
    gateway.on_place = lambda *a: (_ for _ in ()).throw(OrderRejectedException("no funds"))

    assert await cycle().run(make_bot()) == CycleOutcome.ENTRY_REJECTED
    assert repo.committed_trades()[0].status == TRADE_STATUS_CANCELLED
    assert repo.committed_trades()[0].exit_reason == "REJECTED"


async def test_no_order_when_pending_entry_cannot_be_recorded(env):
    repo, gateway, _, cycle = env
    repo.fail_next_commit = True

    assert await cycle().run(make_bot()) == CycleOutcome.ENTRY_NOT_RECORDED
    assert gateway.sent == []
    assert repo.committed_trades() == []


async def test_sell_signal_without_position_sends_nothing(env):
    repo, gateway, _, cycle = env
    assert await cycle(TradeSignal.SELL).run(make_bot()) == CycleOutcome.IGNORED_SELL_WITHOUT_POSITION
    assert gateway.sent == []


async def test_hold_signal_sends_nothing(env):
    _, gateway, _, cycle = env
    assert await cycle(TradeSignal.HOLD).run(make_bot()) == CycleOutcome.NO_SIGNAL
    assert gateway.sent == []


async def test_database_rejects_second_active_trade(env):
    repo, gateway, _, cycle = env
    bot = make_bot()
    await cycle().run(bot)
    # Simulate a concurrent worker that did not see the first trade.
    repo.find_active_by_bot_id = AsyncMock(return_value=[])
    assert await cycle().run(bot) == CycleOutcome.ENTRY_NOT_RECORDED
    assert len(gateway.sent) == 1


# ---- exit --------------------------------------------------------------------


async def _open_position(env, price=50000.0, fee_rate=0.001):
    repo, gateway, _, cycle = env
    gateway.price = price
    gateway.on_place = lambda s, side, q, cid: filled(
        side, q, price, cid, fee_cost=q * fee_rate, fee_currency="BTC"
    )
    bot = make_bot()
    assert await cycle().run(bot) == CycleOutcome.ENTRY_FILLED
    gateway.on_place = None
    return bot


async def test_holds_while_inside_stop_and_target(env):
    repo, gateway, _, cycle = env
    bot = await _open_position(env)
    gateway.price = 50500.0  # +1%
    assert await cycle().run(bot) == CycleOutcome.HOLDING
    assert len(gateway.sent) == 1


async def test_stop_loss_closes_with_pnl_net_of_fees(env):
    repo, gateway, _, cycle = env
    bot = await _open_position(env)
    [opened] = repo.committed_trades()
    seen_at_send = []

    def on_sell(symbol, side, qty, cid):
        seen_at_send.extend(repo.committed_trades())
        price = 48900.0
        return filled(side, qty, price, cid, fee_cost=qty * price * 0.001, fee_currency="USDT")

    gateway.price = 48900.0  # -2.2%
    gateway.on_place = on_sell
    assert await cycle().run(bot) == CycleOutcome.EXIT_FILLED

    assert seen_at_send[0].status == TRADE_STATUS_PENDING_CLOSE
    sell = gateway.sent[-1]
    assert sell[0] == "SELL"
    assert sell[1] == pytest.approx(opened.quantity)  # sells what is actually held

    [closed] = repo.committed_trades()
    proceeds = opened.quantity * 48900.0 * 0.999
    assert closed.status == TRADE_STATUS_CLOSED
    assert closed.exit_reason == "STOP_LOSS"
    assert closed.pnl_usd == pytest.approx(proceeds - 100.0)
    assert closed.pnl_pct == pytest.approx((proceeds - 100.0) / 100.0 * 100)
    assert closed.pnl_usd < (48900.0 - 50000.0) * 0.002  # fees make it worse than gross


async def test_unknown_exit_is_reconciled_not_resent(env):
    repo, gateway, _, cycle = env
    bot = await _open_position(env)
    gateway.price = 52500.0  # take profit
    gateway.on_place = lambda *a: (_ for _ in ()).throw(OrderStateUnknownException("timeout"))

    assert await cycle().run(bot) == CycleOutcome.EXIT_PENDING
    assert await cycle().run(bot) == CycleOutcome.EXIT_PENDING
    sells = [s for s in gateway.sent if s[0] == "SELL"]
    assert len(sells) == 1

    cid = sells[0][2]
    gateway.lookup[cid] = filled("SELL", sells[0][1], 52500.0, cid)
    assert await cycle().run(bot) == CycleOutcome.EXIT_FILLED
    assert repo.committed_trades()[0].status == TRADE_STATUS_CLOSED


async def test_partial_exit_keeps_remainder_open_then_closes_it(env):
    repo, gateway, _, cycle = env
    bot = await _open_position(env)
    held = repo.committed_trades()[0].quantity
    gateway.price = 47000.0

    def half(symbol, side, qty, cid):
        result = filled(side, qty / 2, 47000.0, cid)
        return result

    gateway.on_place = half
    assert await cycle().run(bot) == CycleOutcome.EXIT_PARTIAL
    trade = repo.committed_trades()[0]
    assert trade.status == TRADE_STATUS_OPEN
    assert trade.open_quantity == pytest.approx(held / 2)

    gateway.on_place = None
    assert await cycle().run(bot) == CycleOutcome.EXIT_FILLED
    assert gateway.sent[-1][1] == pytest.approx(held / 2)
    closed = repo.committed_trades()[0]
    assert closed.status == TRADE_STATUS_CLOSED
    assert closed.pnl_usd == pytest.approx(held * 47000.0 - 100.0)


async def test_rejected_exit_returns_to_open(env):
    repo, gateway, _, cycle = env
    bot = await _open_position(env)
    gateway.price = 40000.0
    gateway.on_place = lambda *a: (_ for _ in ()).throw(OrderRejectedException("min qty"))

    assert await cycle().run(bot) == CycleOutcome.EXIT_REJECTED
    trade = repo.committed_trades()[0]
    assert trade.status == TRADE_STATUS_OPEN
    assert trade.exit_client_order_id is None


async def test_legacy_open_trade_without_cost_basis_is_not_traded(env):
    repo, gateway, _, cycle = env
    bot = make_bot()
    legacy = Trade(bot_id=bot.id, symbol=SYMBOL, side="BUY", status=TRADE_STATUS_OPEN,
                   price_executed=None, quantity=0.002)
    await repo.insert(legacy)
    await repo.commit()

    assert await cycle().run(bot) == CycleOutcome.INCONSISTENT
    assert gateway.sent == []


# ---- end to end with the paper gateway --------------------------------------


async def test_paper_round_trip_charges_spread_slippage_and_fees(env):
    repo, _, _, cycle = env
    exchange = make_fake_bybit()
    exchange.fetch_ticker = AsyncMock(return_value={"bid": 49990.0, "ask": 50010.0, "last": 50000.0})
    paper = PaperExchangeGateway(BybitGateway("", "", exchange=exchange), 0.001, 5)
    paper.get_market_snapshot = AsyncMock(
        return_value=MarketData(symbol=SYMBOL, current_price=50000.0, indicators={})
    )
    paper.get_current_price = AsyncMock(return_value=50000.0)
    try:
        bot = make_bot(stop_loss_pct=0.05, take_profit_pct=10.0)  # entry ~0.07% above mid
        assert await cycle(gw=paper).run(bot) == CycleOutcome.ENTRY_FILLED
        assert await cycle(gw=paper).run(bot) == CycleOutcome.EXIT_FILLED

        [trade] = repo.committed_trades()
        # Flat market, yet the round trip loses spread + slippage + 2x fees.
        assert trade.pnl_usd < 0
        buy_price = 50010.0 * 1.0005
        sell_price = 49990.0 * 0.9995
        held = (100.0 / 50000.0) * 0.999  # base fee on the buy
        expected_pnl = held * sell_price * 0.999 - (100.0 / 50000.0) * buy_price
        assert trade.pnl_usd == pytest.approx(expected_pnl)
        assert trade.pnl_pct == pytest.approx(-0.34, abs=0.01)
        exchange.create_order.assert_not_called()
    finally:
        await exchange.close()


# ---- deactivated bots ---------------------------------------------------------


async def test_inactive_bot_never_opens_positions(env):
    _, gateway, _, cycle = env
    assert await cycle().run(make_bot(is_active=False)) == CycleOutcome.BOT_INACTIVE
    assert gateway.sent == []


async def test_inactive_bot_still_protects_its_open_position(env):
    repo, gateway, _, cycle = env
    bot = await _open_position(env)
    bot.deactivate()

    gateway.price = 40000.0  # stop loss
    assert await cycle().run(bot) == CycleOutcome.EXIT_FILLED
    assert repo.committed_trades()[0].status == TRADE_STATUS_CLOSED


async def test_inactive_bot_still_reconciles_pending_entry(env):
    repo, gateway, _, cycle = env
    gateway.on_place = lambda *a: (_ for _ in ()).throw(OrderStateUnknownException("lost"))
    bot = make_bot()
    await cycle().run(bot)
    bot.deactivate()

    cid = gateway.sent[0][2]
    gateway.lookup[cid] = filled("BUY", 0.002, 50000.0, cid)
    assert await cycle().run(bot) == CycleOutcome.ENTRY_FILLED


# ---- exchange lot size and minimums -------------------------------------------


async def test_entry_below_minimum_sends_and_records_nothing(env):
    repo, gateway, _, cycle = env
    outcome = await cycle().run(make_bot(allocated_capital=4.0))  # < 5 USDT min notional
    assert outcome == CycleOutcome.ENTRY_BELOW_MINIMUM
    assert gateway.sent == []
    assert repo.committed_trades() == []


async def test_entry_quantity_is_floored_to_lot_step(env):
    _, gateway, _, cycle = env
    gateway.price = 30000.0  # 100 / 30000 = 0.0033333...
    await cycle().run(make_bot())
    assert gateway.sent[0][1] == 0.003333


async def test_exit_quantity_is_floored_and_dust_written_off(env):
    repo, gateway, _, cycle = env
    gateway.price = 30000.0
    gateway.on_place = lambda s, side, q, cid: filled(
        side, q, 30000.0, cid, fee_cost=q * 0.001, fee_currency="BTC"
    )
    bot = make_bot()
    await cycle().run(bot)
    held = repo.committed_trades()[0].quantity  # 0.003333 * 0.999 = 0.003329667
    assert held == pytest.approx(0.003329667)

    gateway.on_place = None
    gateway.price = 25000.0
    assert await cycle().run(bot) == CycleOutcome.EXIT_FILLED
    assert gateway.sent[-1][1] == 0.003329  # floored to the lot step

    [closed] = repo.committed_trades()
    assert closed.status == TRADE_STATUS_CLOSED
    assert closed.exit_reason == "STOP_LOSS+DUST"
    assert closed.open_quantity == 0.0
    # The unsellable 0.000000667 BTC is booked at zero value.
    assert closed.pnl_usd == pytest.approx(0.003329 * 25000.0 - closed.entry_cost)


async def test_position_below_minimum_is_flagged_not_sent(env):
    repo, gateway, _, cycle = env
    bot = await _open_position(env)
    gateway.rules = TradingRules(amount_step=0.000001, min_amount=1.0, min_cost=5.0)
    gateway.price = 40000.0
    sent_before = len(gateway.sent)

    assert await cycle().run(bot) == CycleOutcome.EXIT_BELOW_MINIMUM
    assert len(gateway.sent) == sent_before
    assert repo.committed_trades()[0].status == TRADE_STATUS_OPEN


# ---- live/backtest parity -------------------------------------------------------


class SwitchableStrategy(IBotStrategy):
    def __init__(self):
        self.signal = TradeSignal.BUY

    @property
    def name(self) -> str:
        return "SWITCH"

    async def analyze(self, market_data):
        return self.signal


async def test_sell_signal_closes_open_position(env):
    repo, gateway, clock, _ = env
    strategy = SwitchableStrategy()
    cycle = BotCycle(trade_repository=repo, gateway=gateway, strategy=strategy,
                     risk_guard=RiskGuard(repo, PERMISSIVE),
                     commit=repo.commit, rollback=repo.rollback, clock=clock)
    bot = make_bot()
    assert await cycle.run(bot) == CycleOutcome.ENTRY_FILLED

    gateway.price = 50500.0  # inside SL/TP
    assert await cycle.run(bot) == CycleOutcome.HOLDING
    strategy.signal = TradeSignal.SELL
    assert await cycle.run(bot) == CycleOutcome.EXIT_FILLED
    assert repo.committed_trades()[0].exit_reason == "SIGNAL"


async def test_no_reentry_within_the_candle_of_the_last_exit(env):
    repo, gateway, _, cycle = env
    gateway.candle_closed_at = datetime.now(timezone.utc) - timedelta(minutes=30)
    bot = await _open_position(env)
    gateway.price = 40000.0
    assert await cycle().run(bot) == CycleOutcome.EXIT_FILLED

    gateway.price = 50000.0
    assert await cycle().run(bot) == CycleOutcome.WAITING_NEXT_CANDLE
    buys = [s for s in gateway.sent if s[0] == "BUY"]
    assert len(buys) == 1

    gateway.candle_closed_at = datetime.now(timezone.utc) + timedelta(seconds=1)
    assert await cycle().run(bot) == CycleOutcome.ENTRY_FILLED


async def test_rejected_entry_is_not_retried_in_the_same_candle(env):
    repo, gateway, _, cycle = env
    gateway.candle_closed_at = datetime.now(timezone.utc) - timedelta(minutes=5)
    gateway.on_place = lambda *a: (_ for _ in ()).throw(OrderRejectedException("no funds"))
    bot = make_bot()
    assert await cycle().run(bot) == CycleOutcome.ENTRY_REJECTED
    for _ in range(3):
        assert await cycle().run(bot) == CycleOutcome.WAITING_NEXT_CANDLE
    assert len(gateway.sent) == 1


# ---- account reconciliation (testnet/live) ---------------------------------------


async def test_entry_refused_when_quote_balance_is_insufficient(env):
    repo, gateway, _, cycle = env
    gateway.balances = {"USDT": 50.0}
    assert await cycle().run(make_bot(allocated_capital=100.0)) == CycleOutcome.INSUFFICIENT_BALANCE
    assert gateway.sent == []
    assert repo.committed_trades() == []


async def test_open_position_missing_from_account_blocks_trading(env):
    repo, gateway, _, cycle = env
    bot = await _open_position(env)
    gateway.balances = {"BTC": 0.0, "USDT": 1000.0}  # coins were sold elsewhere
    gateway.price = 40000.0  # would trigger the stop

    for _ in range(3):
        assert await cycle().run(bot) == CycleOutcome.POSITION_MISMATCH
    assert [s for s in gateway.sent if s[0] == "SELL"] == []
    assert repo.committed_trades()[0].status == TRADE_STATUS_OPEN


async def test_open_position_present_in_account_is_managed(env):
    repo, gateway, _, cycle = env
    bot = await _open_position(env)
    held = repo.committed_trades()[0].quantity
    gateway.balances = {"BTC": held, "USDT": 0.0}
    gateway.price = 40000.0
    assert await cycle().run(bot) == CycleOutcome.EXIT_FILLED


# ---- risk guard integration --------------------------------------------------------


async def test_halted_trading_blocks_entries_but_still_closes_positions(env):
    repo, gateway, clock, _ = env
    bot = await _open_position(env)
    halted = BotCycle(trade_repository=repo, gateway=gateway, strategy=FixedStrategy(TradeSignal.BUY),
                      risk_guard=RiskGuard(repo, RiskLimits(trading_halted=True)),
                      commit=repo.commit, rollback=repo.rollback, clock=clock)
    gateway.price = 40000.0
    assert await halted.run(bot) == CycleOutcome.EXIT_FILLED
    assert await halted.run(bot) == CycleOutcome.RISK_BLOCKED
    assert len([s for s in gateway.sent if s[0] == "BUY"]) == 1


async def test_entry_records_the_decision_context(env):
    repo, gateway, _, cycle = env
    gateway.candle_closed_at = datetime(2026, 10, 10, 12, tzinfo=timezone.utc)
    await cycle().run(make_bot())
    context = repo.committed_trades()[0].entry_context
    assert context["strategy"] == "FIXED"
    assert context["signal"] == "BUY"
    assert context["observed_price"] == 50000.0
    assert context["candle_closed_at"] == "2026-10-10T12:00:00+00:00"


# ---- fees charged in a third currency -------------------------------------------


async def test_third_currency_fee_is_converted_at_market_price(env):
    repo, gateway, _, cycle = env
    gateway.on_place = lambda s, side, q, cid: filled(side, q, 50000.0, cid,
                                                      fee_cost=2.0, fee_currency="MNT")
    prices = {"MNT/USDT": 0.5}
    original_price = gateway.get_current_price

    async def price(symbol):
        return prices.get(symbol) or await original_price(symbol)

    gateway.get_current_price = price
    await cycle().run(make_bot())
    trade = repo.committed_trades()[0]
    assert trade.fee_paid == pytest.approx(1.0)        # 2 MNT x 0.5 USDT
    assert trade.quantity == pytest.approx(0.002)      # base quantity untouched


async def test_unconvertible_fee_is_reported_not_added_raw(env, caplog):
    repo, gateway, _, cycle = env
    gateway.on_place = lambda s, side, q, cid: filled(side, q, 50000.0, cid,
                                                      fee_cost=2.0, fee_currency="XYZ")

    async def no_market(symbol):
        raise GatewayException("no market")

    gateway.get_current_price = no_market
    await cycle().run(make_bot())
    assert repo.committed_trades()[0].fee_paid == 0.0
    assert any("could not be converted" in r.getMessage() for r in caplog.records)


# ---- per-order maximums ------------------------------------------------------------


async def test_entry_above_the_order_maximum_is_capped(env):
    repo, gateway, _, cycle = env
    gateway.rules = TradingRules(amount_step=0.000001, min_amount=0.000048, min_cost=5.0,
                                 max_amount=0.001)
    assert await cycle().run(make_bot(allocated_capital=100.0)) == CycleOutcome.ENTRY_FILLED
    assert gateway.sent[-1][1] == pytest.approx(0.001)  # 100 USDT / 50 000 = 0.002, capped
    assert repo.committed_trades()[0].open_quantity == pytest.approx(0.001)


async def test_exit_above_the_order_maximum_is_split(env):
    repo, gateway, _, cycle = env
    bot = await _open_position(env)  # 0.002 BTC bought, 0.000002 BTC fee -> 0.001998 held
    gateway.rules = TradingRules(amount_step=0.000001, min_amount=0.000048, min_cost=5.0,
                                 max_amount=0.001)
    gateway.price = 40000.0  # below the stop

    assert await cycle().run(bot) == CycleOutcome.EXIT_PARTIAL
    assert gateway.sent[-1][:2] == ("SELL", pytest.approx(0.001))
    [trade] = repo.committed_trades()
    assert trade.status == TRADE_STATUS_OPEN
    assert trade.open_quantity == pytest.approx(0.000998)
