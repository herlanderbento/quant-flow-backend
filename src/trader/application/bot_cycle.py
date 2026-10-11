import logging
from datetime import datetime, timedelta, timezone
from enum import Enum
from typing import Awaitable, Callable
from uuid import uuid4

from shared.application.log_context import bind_log_context
from shared.domain.exceptions import GatewayException, OrderRejectedException
from trader.application.order_sizing import calculate_order_quantity
from trader.application.risk_guard import RiskGuard
from trader.application.risk_management import evaluate_exit
from trader.domain.bot import Bot
from trader.domain.interface.exchange_gateway_interface import (
    IExchangeGateway,
    OrderResult,
)
from trader.domain.interface.strategy_interface import (
    IBotStrategy,
    MarketData,
    TradeSignal,
)
from trader.domain.repositories.trade_repository import ITradeRepository
from trader.domain.trade import (
    TRADE_STATUS_PENDING_CLOSE,
    TRADE_STATUS_PENDING_OPEN,
    Trade,
    TradePendingCommand,
)

logger = logging.getLogger(__name__)

# How long an order may stay invisible on the exchange before we conclude it was never placed.
DEFAULT_PENDING_GRACE = timedelta(minutes=5)
# Exchange balance may differ slightly from our books (rounding, dust).
BALANCE_TOLERANCE = 0.01


class CycleOutcome(str, Enum):
    NO_SIGNAL = "NO_SIGNAL"
    BOT_INACTIVE = "BOT_INACTIVE"
    ENTRY_BELOW_MINIMUM = "ENTRY_BELOW_MINIMUM"
    WAITING_NEXT_CANDLE = "WAITING_NEXT_CANDLE"
    INSUFFICIENT_BALANCE = "INSUFFICIENT_BALANCE"
    POSITION_MISMATCH = "POSITION_MISMATCH"
    RISK_BLOCKED = "RISK_BLOCKED"
    EXIT_BELOW_MINIMUM = "EXIT_BELOW_MINIMUM"
    IGNORED_SELL_WITHOUT_POSITION = "IGNORED_SELL_WITHOUT_POSITION"
    ENTRY_NOT_RECORDED = "ENTRY_NOT_RECORDED"
    ENTRY_FILLED = "ENTRY_FILLED"
    ENTRY_PENDING = "ENTRY_PENDING"
    ENTRY_REJECTED = "ENTRY_REJECTED"
    ENTRY_CANCELLED = "ENTRY_CANCELLED"
    HOLDING = "HOLDING"
    EXIT_NOT_RECORDED = "EXIT_NOT_RECORDED"
    EXIT_FILLED = "EXIT_FILLED"
    EXIT_PARTIAL = "EXIT_PARTIAL"
    EXIT_PENDING = "EXIT_PENDING"
    EXIT_REJECTED = "EXIT_REJECTED"
    EXIT_NOT_FOUND = "EXIT_NOT_FOUND"
    RECONCILE_FAILED = "RECONCILE_FAILED"
    INCONSISTENT = "INCONSISTENT"


def _decision_context(strategy: IBotStrategy, market: MarketData) -> dict:
    context = {
        "strategy": strategy.name,
        "signal": TradeSignal.BUY.value,
        "observed_price": market.current_price,
        "indicators": {k: v for k, v in market.indicators.items() if isinstance(v, (int, float))},
        "candle_closed_at": (
            market.candle_closed_at.isoformat() if market.candle_closed_at else None
        ),
    }
    decision = getattr(strategy, "last_decision", None)
    if decision is not None and getattr(decision, "probability", None) is not None:
        context["model"] = {
            "version": decision.model_version,
            "probability": decision.probability,
            "feature_candle_close": decision.feature_candle_close.isoformat(),
        }
    return context


def new_client_order_id() -> str:
    # Bybit orderLinkId accepts up to 36 characters.
    return f"qf{uuid4().hex}"


class BotCycle:
    """
    One decision cycle for one bot.

    Every order is recorded and committed *before* it is sent, tagged with a
    client order id. If the outcome is unknown the trade stays pending and is
    reconciled against the exchange on later cycles; it is never re-sent blindly.
    """

    def __init__(
        self,
        *,
        trade_repository: ITradeRepository,
        gateway: IExchangeGateway,
        strategy: IBotStrategy,
        risk_guard: RiskGuard,
        commit: Callable[[], Awaitable[None]],
        rollback: Callable[[], Awaitable[None]],
        client_order_id_factory: Callable[[], str] = new_client_order_id,
        clock: Callable[[], datetime] = lambda: datetime.now(timezone.utc),
        pending_grace: timedelta = DEFAULT_PENDING_GRACE,
    ):
        self.trades = trade_repository
        self.gateway = gateway
        self.strategy = strategy
        self.risk_guard = risk_guard
        self.commit = commit
        self.rollback = rollback
        self.new_client_order_id = client_order_id_factory
        self.clock = clock
        self.pending_grace = pending_grace
        # Wall-clock time of the last successful market snapshot in this cycle.
        self.market_data_at: datetime | None = None

    async def _snapshot(self, symbol: str) -> MarketData:
        market = await self.gateway.get_market_snapshot(symbol)
        self.market_data_at = self.clock()
        return market

    async def run(self, bot: Bot) -> CycleOutcome:
        active = await self.trades.find_active_by_bot_id(bot.id)
        if len(active) > 1:
            logger.error("Bot %s has %d active trades; refusing to act.", bot.id, len(active))
            return CycleOutcome.INCONSISTENT

        if not active:
            if not bot.is_active:
                # A deactivated bot only winds down what it already holds.
                return CycleOutcome.BOT_INACTIVE
            return await self._maybe_enter(bot)

        trade = active[0]
        bind_log_context(trade_id=str(trade.id.value), client_order_id=trade.client_order_id)
        if trade.status == TRADE_STATUS_PENDING_OPEN:
            return await self._reconcile_entry(trade)
        if trade.status == TRADE_STATUS_PENDING_CLOSE:
            return await self._reconcile_exit(trade)
        return await self._manage_open_position(bot, trade)

    # ---- entry -------------------------------------------------------------

    async def _maybe_enter(self, bot: Bot) -> CycleOutcome:
        market = await self._snapshot(bot.symbol)
        signal = await self.strategy.analyze(market)

        if signal == TradeSignal.SELL:
            # Spot is long-only: selling without a position would sell the user's own coins.
            return CycleOutcome.IGNORED_SELL_WITHOUT_POSITION
        if signal != TradeSignal.BUY:
            return CycleOutcome.NO_SIGNAL

        # One entry attempt per closed candle, as in the backtest.
        last = await self.trades.find_latest_final_by_bot_id(bot.id)
        if (
            last is not None
            and last.closed_at is not None
            and market.candle_closed_at is not None
            and last.closed_at >= market.candle_closed_at
        ):
            return CycleOutcome.WAITING_NEXT_CANDLE

        verdict = await self.risk_guard.check_entry(bot)
        if not verdict.allowed:
            logger.warning("Bot %s entry blocked by risk limit %s.", bot.id, verdict.reason)
            return CycleOutcome.RISK_BLOCKED

        rules = await self.gateway.get_trading_rules(bot.symbol)
        quantity = rules.limit_quantity(
            calculate_order_quantity(bot.allocated_capital, market.current_price),
            market.current_price,
        )
        if not rules.is_tradable(quantity, market.current_price):
            logger.warning(
                "Bot %s: %s %s is below the exchange minimum; no order.",
                bot.id,
                quantity,
                bot.symbol,
            )
            return CycleOutcome.ENTRY_BELOW_MINIMUM

        quote = bot.symbol.split("/", 1)[1]
        available = await self.gateway.get_balance(quote)
        if available is not None and available < bot.allocated_capital:
            logger.warning(
                "Bot %s: %s %s available, %s allocated; no order.",
                bot.id,
                available,
                quote,
                bot.allocated_capital,
            )
            return CycleOutcome.INSUFFICIENT_BALANCE

        trade = Trade.open_pending(
            TradePendingCommand(
                bot_id=bot.id,
                symbol=bot.symbol,
                side="BUY",
                requested_quantity=quantity,
                client_order_id=self.new_client_order_id(),
                entry_context=_decision_context(self.strategy, market),
            )
        )

        bind_log_context(trade_id=str(trade.id.value), client_order_id=trade.client_order_id)
        try:
            await self.trades.insert(trade)
            await self.commit()
        except Exception:
            # Includes the unique index refusing a second active trade: nothing was sent.
            await self.rollback()
            logger.exception("Could not record pending entry for bot %s; no order sent.", bot.id)
            return CycleOutcome.ENTRY_NOT_RECORDED

        try:
            order = await self.gateway.place_market_order(
                bot.symbol, "BUY", quantity, trade.client_order_id
            )
        except OrderRejectedException as e:
            logger.warning("Entry rejected for bot %s: %s", bot.id, e)
            trade.cancel_entry("REJECTED")
            await self._save(trade)
            return CycleOutcome.ENTRY_REJECTED
        except Exception:
            logger.exception(
                "Entry outcome unknown for bot %s (%s); will reconcile.",
                bot.id,
                trade.client_order_id,
            )
            return CycleOutcome.ENTRY_PENDING

        return await self._apply_entry_result(trade, order)

    async def _reconcile_entry(self, trade: Trade) -> CycleOutcome:
        try:
            order = await self.gateway.get_order_by_client_id(trade.symbol, trade.client_order_id)
        except GatewayException:
            logger.exception("Could not reconcile entry %s.", trade.client_order_id)
            return CycleOutcome.RECONCILE_FAILED

        if order is None:
            if self.clock() - trade.updated_at >= self.pending_grace:
                logger.warning(
                    "Entry %s never appeared on the exchange; cancelling.", trade.client_order_id
                )
                trade.cancel_entry("NOT_FOUND_ON_EXCHANGE")
                await self._save(trade)
                return CycleOutcome.ENTRY_CANCELLED
            return CycleOutcome.ENTRY_PENDING

        return await self._apply_entry_result(trade, order)

    async def _apply_entry_result(self, trade: Trade, order: OrderResult) -> CycleOutcome:
        if not order.is_final:
            return CycleOutcome.ENTRY_PENDING

        if not order.has_fill:
            trade.cancel_entry(f"NOT_FILLED_{order.status.upper()}")
            await self._save(trade)
            return CycleOutcome.ENTRY_REJECTED

        base = trade.symbol.split("/", 1)[0]
        entry_fee = await self._fee_in_quote(order, trade.symbol)
        trade.confirm_entry(
            exchange_order_id=order.order_id,
            average_price=order.average_price,
            net_quantity=order.net_base_quantity(base),
            gross_cost=order.average_price * order.filled_quantity,
            fee_in_quote=entry_fee,
        )
        await self._save(trade)
        logger.info(
            "Entry filled %s: %s %s @ %s",
            trade.client_order_id,
            trade.quantity,
            trade.symbol,
            trade.price_executed,
        )
        return CycleOutcome.ENTRY_FILLED

    # ---- exit --------------------------------------------------------------

    async def _manage_open_position(self, bot: Bot, trade: Trade) -> CycleOutcome:
        if trade.price_executed is None or trade.entry_cost is None or not trade.open_quantity:
            logger.error("Open trade %s is missing entry data; manual review needed.", trade.id)
            return CycleOutcome.INCONSISTENT

        base = trade.symbol.split("/", 1)[0]
        held = await self.gateway.get_balance(base)
        if held is not None:
            # Every bot trading this asset on the same account must be covered.
            expected = await self.trades.open_base_quantity(bot.credential_id, base)
            if held < max(expected, trade.open_quantity) * (1 - BALANCE_TOLERANCE):
                logger.error(
                    "Account holds %s %s but open trades on this credential need %s; "
                    "manual review needed (trade %s).",
                    held,
                    base,
                    expected,
                    trade.id,
                )
                return CycleOutcome.POSITION_MISMATCH

        market = await self._snapshot(trade.symbol)
        current_price = market.current_price
        decision = evaluate_exit(
            side=trade.side,
            entry_price=trade.price_executed,
            current_price=current_price,
            stop_loss_pct=bot.stop_loss_pct,
            take_profit_pct=bot.take_profit_pct,
        )
        exit_reason = decision.reason
        if not decision.should_exit:
            # Same exit rule as the backtest: a SELL signal closes the long.
            if await self.strategy.analyze(market) != TradeSignal.SELL:
                return CycleOutcome.HOLDING
            exit_reason = "SIGNAL"

        rules = await self.gateway.get_trading_rules(trade.symbol)
        # Above the per-order maximum the exit is split; the remainder goes through
        # the partial-exit path and is sold on later cycles.
        exit_quantity = rules.limit_quantity(trade.open_quantity, current_price)
        if not rules.is_tradable(exit_quantity, current_price):
            if trade.open_quantity < trade.quantity:
                # Leftover from a partial exit that can no longer be sold.
                trade.write_off_remainder()
                await self._save(trade)
                return CycleOutcome.EXIT_FILLED
            logger.error(
                "Trade %s: position %s %s is below the exchange minimum and cannot be sold.",
                trade.id,
                trade.open_quantity,
                trade.symbol,
            )
            return CycleOutcome.EXIT_BELOW_MINIMUM

        try:
            trade.start_exit(client_order_id=self.new_client_order_id(), reason=exit_reason)
            await self.trades.update(trade)
            await self.commit()
        except Exception:
            await self.rollback()
            logger.exception("Could not record exit for trade %s; no order sent.", trade.id)
            return CycleOutcome.EXIT_NOT_RECORDED

        try:
            order = await self.gateway.place_market_order(
                trade.symbol, "SELL", exit_quantity, trade.exit_client_order_id
            )
        except OrderRejectedException as e:
            logger.error("Exit rejected for trade %s: %s", trade.id, e)
            trade.abort_exit()
            await self._save(trade)
            return CycleOutcome.EXIT_REJECTED
        except Exception:
            logger.exception(
                "Exit outcome unknown for trade %s (%s); will reconcile.",
                trade.id,
                trade.exit_client_order_id,
            )
            return CycleOutcome.EXIT_PENDING

        return await self._apply_exit_result(trade, order)

    async def _reconcile_exit(self, trade: Trade) -> CycleOutcome:
        try:
            order = await self.gateway.get_order_by_client_id(
                trade.symbol, trade.exit_client_order_id
            )
        except GatewayException:
            logger.exception("Could not reconcile exit %s.", trade.exit_client_order_id)
            return CycleOutcome.RECONCILE_FAILED

        if order is None:
            if self.clock() - trade.updated_at >= self.pending_grace:
                logger.warning(
                    "Exit %s never appeared on the exchange; position still open.",
                    trade.exit_client_order_id,
                )
                trade.abort_exit()
                await self._save(trade)
                return CycleOutcome.EXIT_NOT_FOUND
            return CycleOutcome.EXIT_PENDING

        return await self._apply_exit_result(trade, order)

    async def _apply_exit_result(self, trade: Trade, order: OrderResult) -> CycleOutcome:
        if not order.is_final:
            return CycleOutcome.EXIT_PENDING

        if not order.has_fill:
            trade.abort_exit()
            await self._save(trade)
            return CycleOutcome.EXIT_REJECTED

        exit_fee = await self._fee_in_quote(order, trade.symbol)
        trade.register_exit_fill(
            exchange_order_id=order.order_id,
            average_price=order.average_price,
            filled_quantity=order.filled_quantity,
            fee_in_quote=exit_fee,
        )
        if trade.is_active:
            rules = await self.gateway.get_trading_rules(trade.symbol)
            remainder = rules.floor_quantity(trade.open_quantity)
            if not rules.is_tradable(remainder, order.average_price):
                trade.write_off_remainder()
        await self._save(trade)

        if trade.is_active:
            logger.warning(
                "Partial exit for trade %s; %s %s still open.",
                trade.id,
                trade.open_quantity,
                trade.symbol,
            )
            return CycleOutcome.EXIT_PARTIAL

        logger.info(
            "Position closed %s (%s): pnl %.8f (%.4f%%)",
            trade.id,
            trade.exit_reason,
            trade.pnl_usd,
            trade.pnl_pct,
        )
        return CycleOutcome.EXIT_FILLED

    async def _fee_in_quote(self, order: OrderResult, symbol: str) -> float:
        base, quote = symbol.split("/", 1)
        fee = order.fee_in_quote(base, quote)
        if fee is not None:
            return fee
        # Charged in a third currency (e.g. an exchange discount token): convert at market.
        try:
            rate = await self.gateway.get_current_price(f"{order.fee_currency}/{quote}")
            return order.fee_cost * rate
        except Exception:
            logger.error(
                "Fee of %s %s on order %s could not be converted to %s; PnL excludes it.",
                order.fee_cost,
                order.fee_currency,
                order.order_id,
                quote,
                extra={"fee_unconverted": True},
            )
            return 0.0

    async def _save(self, trade: Trade) -> None:
        await self.trades.update(trade)
        await self.commit()
