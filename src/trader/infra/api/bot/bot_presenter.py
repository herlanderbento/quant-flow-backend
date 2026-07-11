from datetime import datetime
from uuid import UUID
from pydantic import BaseModel, ConfigDict

from typing import Any

from shared.infra.api.presenter import CollectionPresenter, meta_from_output
from trader.application.use_cases.bot.common.bot_output import BotOutput


class BotPresenter(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: UUID
    user_id: UUID
    credential_id: UUID
    name: str
    symbol: str
    strategy_type: str
    is_active: bool
    allocated_capital: float
    stop_loss_pct: float
    take_profit_pct: float
    created_at: datetime
    updated_at: datetime

    @classmethod
    def from_output(cls, output: BotOutput) -> "BotPresenter":
        return cls(
            id=UUID(output.id),
            user_id=UUID(output.user_id),
            credential_id=UUID(output.credential_id),
            name=output.name,
            symbol=output.symbol,
            strategy_type=output.strategy_type,
            is_active=output.is_active,
            allocated_capital=output.allocated_capital,
            stop_loss_pct=output.stop_loss_pct,
            take_profit_pct=output.take_profit_pct,
            created_at=output.created_at,
            updated_at=output.updated_at,
        )


class BotCollectionPresenter(CollectionPresenter[BotPresenter]):
    @classmethod
    def from_output(cls, output: Any) -> "BotCollectionPresenter":
        return cls(
            data=[BotPresenter.from_output(item) for item in output.items],
            meta=meta_from_output(output),
        )
