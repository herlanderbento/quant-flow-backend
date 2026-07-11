from dataclasses import dataclass
import datetime

from trader.domain.bot import Bot


@dataclass(frozen=True)
class BotOutput:
    id: str
    user_id: str
    credential_id: str
    name: str
    symbol: str
    strategy_type: str
    is_active: bool
    allocated_capital: float
    stop_loss_pct: float
    take_profit_pct: float
    created_at: datetime.datetime
    updated_at: datetime.datetime

    @classmethod
    def from_entity(cls, bot: Bot) -> "BotOutput":
        return cls(
            id=bot.id.value,
            user_id=bot.user_id.value,
            credential_id=bot.credential_id.value,
            name=bot.name,
            symbol=bot.symbol,
            strategy_type=bot.strategy_type,
            is_active=bot.is_active,
            allocated_capital=bot.allocated_capital,
            stop_loss_pct=bot.stop_loss_pct,
            take_profit_pct=bot.take_profit_pct,
            created_at=bot.created_at,
            updated_at=bot.updated_at,
        )
