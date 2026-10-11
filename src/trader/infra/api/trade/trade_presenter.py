from datetime import datetime
from uuid import UUID

from pydantic import BaseModel, ConfigDict
from typing import Any

from shared.infra.api.presenter import CollectionPresenter, meta_from_output
from trader.application.use_cases.trade.common.trade_output import TradeOutput


class TradePresenter(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: UUID
    bot_id: UUID
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
    executed_at: datetime
    closed_at: datetime | None

    @classmethod
    def from_output(cls, output: TradeOutput) -> "TradePresenter":
        return cls(
            id=UUID(output.id),
            bot_id=UUID(output.bot_id),
            symbol=output.symbol,
            side=output.side,
            status=output.status,
            price_executed=output.price_executed,
            quantity=output.quantity,
            open_quantity=output.open_quantity,
            pnl_usd=output.pnl_usd,
            pnl_pct=output.pnl_pct,
            fee_paid=output.fee_paid,
            exchange_order_id=output.exchange_order_id,
            exit_price=output.exit_price,
            exit_reason=output.exit_reason,
            executed_at=output.executed_at,
            closed_at=output.closed_at,
        )


class TradeCollectionPresenter(CollectionPresenter[TradePresenter]):
    @classmethod
    def from_output(cls, output: Any) -> "TradeCollectionPresenter":
        return cls(
            data=[TradePresenter.from_output(item) for item in output.items],
            meta=meta_from_output(output),
        )
