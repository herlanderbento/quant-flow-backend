from uuid import UUID

from shared.domain.exceptions import InvalidArgumentException

from trader.domain.ai_prediction import AIPredictionId

from trader.domain.bot import BotId

from dataclasses import dataclass, field

from datetime import datetime, timezone

from shared.domain.entity import AggregateRoot

from typing import Annotated

from pydantic import Strict


TRADE_STATUS_OPEN = "OPEN"

TRADE_STATUS_CLOSED = "CLOSED"

TRADE_STATUS_CANCELLED = "CANCELLED"

VALID_TRADE_STATUSES = frozenset(
    {TRADE_STATUS_OPEN, TRADE_STATUS_CLOSED, TRADE_STATUS_CANCELLED}
)


@dataclass
class TradeCreateCommand:

    bot_id: BotId

    ai_prediction_id: AIPredictionId | None

    symbol: str

    side: str  # 'BUY', 'SELL'

    status: str  # 'OPEN', 'CLOSED', 'CANCELLED'

    price_executed: float

    quantity: float

    pnl_usd: float | None = None

    pnl_pct: float | None = None

    fee_paid: float | None = None

    exchange_order_id: str | None = None

    closed_at: datetime | None = None


class TradeId(UUID):

    pass


@dataclass(slots=True, kw_only=True)
class Trade(AggregateRoot):
    id: TradeId = field(default_factory=TradeId)
    bot_id: BotId
    ai_prediction_id: AIPredictionId | None
    symbol: str
    side: str  # 'BUY', 'SELL'
    status: str  # 'OPEN', 'CLOSED', 'CANCELLED'
    price_executed: float
    quantity: float
    pnl_usd: Annotated[float | None, Strict()] = None
    pnl_pct: Annotated[float | None, Strict()] = None
    fee_paid: Annotated[float | None, Strict()] = None
    exchange_order_id: Annotated[str | None, Strict()] = None
    executed_at: Annotated[datetime, Strict()] = field(
        default_factory=lambda: datetime.now(timezone.utc)
    )
    closed_at: Annotated[datetime | None, Strict()] = None

    @staticmethod
    def create(command: TradeCreateCommand) -> "Trade":
        trade = Trade(
            bot_id=command.bot_id,
            ai_prediction_id=command.ai_prediction_id,
            symbol=command.symbol,
            side=command.side,
            status=command.status,
            price_executed=command.price_executed,
            quantity=command.quantity,
            pnl_usd=command.pnl_usd,
            pnl_pct=command.pnl_pct,
            fee_paid=command.fee_paid,
            exchange_order_id=command.exchange_order_id,
            executed_at=datetime.now(timezone.utc),
            closed_at=None,
        )
        trade.validate()
        return trade

    @property
    def entity_id(self) -> TradeId:
        return self.id

    def _require_open(self) -> None:
        if self.status != TRADE_STATUS_OPEN:
            raise InvalidArgumentException("Trade is not open.")

    def close(self, closed_at: datetime) -> None:
        self._require_open()
        self.status = TRADE_STATUS_CLOSED
        self.closed_at = closed_at
        self.validate()

    def close_with_pnl(self, *, exit_price: float, closed_at: datetime) -> None:
        self._require_open()

        if self.side == "BUY":
            self.pnl_usd = (exit_price - self.price_executed) * self.quantity
            self.pnl_pct = (
                (exit_price - self.price_executed) / self.price_executed
            ) * 100
        else:
            self.pnl_usd = (self.price_executed - exit_price) * self.quantity
            self.pnl_pct = (
                (self.price_executed - exit_price) / self.price_executed
            ) * 100
        self.close(closed_at)

    def cancel(self) -> None:
        self._require_open()
        self.status = TRADE_STATUS_CANCELLED
        self.closed_at = datetime.now(timezone.utc)
        self.validate()

    def validate(self) -> None:
        if self.status not in VALID_TRADE_STATUSES:
            raise InvalidArgumentException("Invalid trade status.")
