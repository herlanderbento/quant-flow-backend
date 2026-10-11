from dataclasses import dataclass
import datetime

from trader.domain.trade import Trade


@dataclass(frozen=True)
class TradeOutput:
    id: str
    bot_id: str
    symbol: str
    side: str
    status: str
    price_executed: float | None
    quantity: float
    open_quantity: float | None
    pnl_usd: float | None
    pnl_pct: float | None
    fee_paid: float | None
    exchange_order_id: str | None
    exit_price: float | None
    exit_reason: str | None
    executed_at: datetime.datetime
    closed_at: datetime.datetime | None

    @classmethod
    def from_entity(cls, trade: Trade) -> "TradeOutput":
        return cls(
            id=str(trade.id.value),
            bot_id=str(trade.bot_id.value),
            symbol=trade.symbol,
            side=trade.side,
            status=trade.status,
            price_executed=trade.price_executed,
            quantity=trade.quantity,
            open_quantity=trade.open_quantity,
            pnl_usd=trade.pnl_usd,
            pnl_pct=trade.pnl_pct,
            fee_paid=trade.fee_paid,
            exchange_order_id=trade.exchange_order_id,
            exit_price=trade.exit_price,
            exit_reason=trade.exit_reason,
            executed_at=trade.executed_at,
            closed_at=trade.closed_at,
        )
