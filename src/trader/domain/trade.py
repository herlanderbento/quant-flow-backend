from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Annotated

from pydantic import Strict

from shared.domain.entity import AggregateRoot
from shared.domain.exceptions import InvalidArgumentException
from shared.domain.value_objects import Uuid
from trader.domain.ai_prediction import AIPredictionId
from trader.domain.bot import BotId


# Entry order recorded locally but not yet confirmed by the exchange.
TRADE_STATUS_PENDING_OPEN = "PENDING_OPEN"
TRADE_STATUS_OPEN = "OPEN"
# Exit order recorded locally but not yet confirmed by the exchange.
TRADE_STATUS_PENDING_CLOSE = "PENDING_CLOSE"
TRADE_STATUS_CLOSED = "CLOSED"
# Entry order never executed.
TRADE_STATUS_CANCELLED = "CANCELLED"

VALID_TRADE_STATUSES = frozenset(
    {
        TRADE_STATUS_PENDING_OPEN,
        TRADE_STATUS_OPEN,
        TRADE_STATUS_PENDING_CLOSE,
        TRADE_STATUS_CLOSED,
        TRADE_STATUS_CANCELLED,
    }
)
# A bot may hold at most one trade in any of these states.
ACTIVE_TRADE_STATUSES = frozenset(
    {TRADE_STATUS_PENDING_OPEN, TRADE_STATUS_OPEN, TRADE_STATUS_PENDING_CLOSE}
)

# Remaining quantity below this fraction of the position counts as fully closed.
DUST_FRACTION = 1e-6


@dataclass
class TradePendingCommand:
    bot_id: BotId
    symbol: str
    side: str  # 'BUY' (spot is long-only)
    requested_quantity: float
    client_order_id: str
    ai_prediction_id: AIPredictionId | None = None
    # What the decision was based on: strategy, indicators, candle, observed price.
    entry_context: dict | None = None


class TradeId(Uuid):
    pass


def _now() -> datetime:
    return datetime.now(timezone.utc)


@dataclass(slots=True, kw_only=True)
class Trade(AggregateRoot):
    id: TradeId = field(default_factory=TradeId)
    bot_id: BotId
    ai_prediction_id: AIPredictionId | None = None
    symbol: str
    side: str  # 'BUY', 'SELL'
    status: str
    client_order_id: str | None = None
    entry_context: dict | None = None
    # Average entry price; None until the entry is confirmed.
    price_executed: float | None = None
    # Requested quantity while pending, then base quantity held net of fees.
    quantity: float
    open_quantity: float | None = None
    # Quote spent on entry including fees; the cost basis for PnL.
    entry_cost: float | None = None
    pnl_usd: Annotated[float | None, Strict()] = None
    pnl_pct: Annotated[float | None, Strict()] = None
    # Total fees in quote currency (entry + exit).
    fee_paid: Annotated[float | None, Strict()] = None
    exchange_order_id: Annotated[str | None, Strict()] = None
    exit_client_order_id: str | None = None
    exit_order_id: str | None = None
    exit_price: float | None = None
    exit_reason: str | None = None
    executed_at: Annotated[datetime, Strict()] = field(default_factory=_now)
    updated_at: datetime = field(default_factory=_now)
    closed_at: Annotated[datetime | None, Strict()] = None

    @staticmethod
    def open_pending(command: TradePendingCommand) -> "Trade":
        if command.side != "BUY":
            raise InvalidArgumentException("Spot trades can only be opened with BUY.")
        if command.requested_quantity <= 0:
            raise InvalidArgumentException("requested_quantity must be greater than zero.")
        if not command.client_order_id:
            raise InvalidArgumentException("client_order_id is required.")

        trade = Trade(
            bot_id=command.bot_id,
            ai_prediction_id=command.ai_prediction_id,
            symbol=command.symbol,
            side=command.side,
            status=TRADE_STATUS_PENDING_OPEN,
            client_order_id=command.client_order_id,
            entry_context=command.entry_context,
            quantity=command.requested_quantity,
        )
        trade.validate()
        return trade

    @property
    def entity_id(self) -> TradeId:
        return self.id

    @property
    def is_active(self) -> bool:
        return self.status in ACTIVE_TRADE_STATUSES

    def _require(self, status: str) -> None:
        if self.status != status:
            raise InvalidArgumentException(
                f"Trade is {self.status}, expected {status}."
            )

    def _touch(self) -> None:
        self.updated_at = _now()

    def confirm_entry(
        self,
        *,
        exchange_order_id: str,
        average_price: float,
        net_quantity: float,
        gross_cost: float,
        fee_in_quote: float,
    ) -> None:
        self._require(TRADE_STATUS_PENDING_OPEN)
        if average_price <= 0 or net_quantity <= 0 or gross_cost <= 0:
            raise InvalidArgumentException("Entry fill must have positive price and quantity.")

        self.status = TRADE_STATUS_OPEN
        self.exchange_order_id = exchange_order_id
        self.price_executed = average_price
        self.quantity = net_quantity
        self.open_quantity = net_quantity
        # Fees charged in base already reduced net_quantity; gross_cost covers them.
        self.entry_cost = gross_cost
        self.fee_paid = fee_in_quote
        self.pnl_usd = 0.0
        self.executed_at = _now()
        self._touch()

    def cancel_entry(self, reason: str) -> None:
        self._require(TRADE_STATUS_PENDING_OPEN)
        self.status = TRADE_STATUS_CANCELLED
        self.exit_reason = reason
        self.closed_at = _now()
        self._touch()

    def start_exit(self, *, client_order_id: str, reason: str) -> None:
        self._require(TRADE_STATUS_OPEN)
        if not client_order_id:
            raise InvalidArgumentException("client_order_id is required.")
        self.status = TRADE_STATUS_PENDING_CLOSE
        self.exit_client_order_id = client_order_id
        self.exit_reason = reason
        self._touch()

    def abort_exit(self) -> None:
        """The exit order was not executed at all: the position is still fully open."""
        self._require(TRADE_STATUS_PENDING_CLOSE)
        self.status = TRADE_STATUS_OPEN
        self.exit_client_order_id = None
        self._touch()

    def register_exit_fill(
        self,
        *,
        exchange_order_id: str,
        average_price: float,
        filled_quantity: float,
        fee_in_quote: float,
    ) -> None:
        self._require(TRADE_STATUS_PENDING_CLOSE)
        if average_price <= 0 or filled_quantity <= 0:
            raise InvalidArgumentException("Exit fill must have positive price and quantity.")

        open_quantity = self.open_quantity if self.open_quantity is not None else self.quantity
        filled_quantity = min(filled_quantity, open_quantity)
        cost_basis = self.entry_cost * (filled_quantity / self.quantity)
        proceeds = average_price * filled_quantity - fee_in_quote

        self.pnl_usd = (self.pnl_usd or 0.0) + proceeds - cost_basis
        self.fee_paid = (self.fee_paid or 0.0) + fee_in_quote
        self.exit_order_id = exchange_order_id
        self.exit_price = average_price
        self.open_quantity = open_quantity - filled_quantity
        # Kept as the audit trail of the executed exit; a new exit attempt replaces it.

        if self.open_quantity <= self.quantity * DUST_FRACTION:
            self.open_quantity = 0.0
            self.status = TRADE_STATUS_CLOSED
            self.pnl_pct = (self.pnl_usd / self.entry_cost) * 100
            self.closed_at = _now()
        else:
            # Partial exit: keep managing the remainder.
            self.status = TRADE_STATUS_OPEN
        self._touch()

    def write_off_remainder(self) -> None:
        """
        Close a position whose remainder is below the exchange minimum and cannot be sold.
        The remainder's cost basis is booked as a loss (conservative).
        """
        self._require(TRADE_STATUS_OPEN)
        remainder = self.open_quantity or 0.0
        self.pnl_usd = (self.pnl_usd or 0.0) - self.entry_cost * (remainder / self.quantity)
        self.open_quantity = 0.0
        self.status = TRADE_STATUS_CLOSED
        self.pnl_pct = (self.pnl_usd / self.entry_cost) * 100
        self.exit_reason = f"{self.exit_reason or 'EXIT'}+DUST"
        self.closed_at = _now()
        self._touch()

    def validate(self) -> None:
        if self.status not in VALID_TRADE_STATUSES:
            raise InvalidArgumentException("Invalid trade status.")
