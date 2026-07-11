from dataclasses import dataclass, field
import datetime
from typing import Annotated

from pydantic import Strict

from account.domain.credential import CredentialId
from account.domain.user import UserId
from shared.domain.entity import AggregateRoot
from shared.domain.exceptions import EntityValidationException
from shared.domain.value_objects import Uuid


VALID_STRATEGY_TYPES = {
    "RSI_SIMPLE",
    "SMA_RSI",
    "LSTM_AI_PREDICTOR",
    "SCALPER_LSTM",
}


@dataclass
class BotCreateCommand:
    user_id: UserId
    credential_id: CredentialId
    name: str
    symbol: str
    strategy_type: str
    is_active: bool
    allocated_capital: float
    stop_loss_pct: float
    take_profit_pct: float


class BotId(Uuid):
    pass


@dataclass(slots=True, kw_only=True)
class Bot(AggregateRoot):
    id: BotId = field(default_factory=BotId)
    user_id: UserId
    credential_id: CredentialId
    name: str
    symbol: str
    strategy_type: str
    is_active: bool | None = False
    allocated_capital: float
    stop_loss_pct: float
    take_profit_pct: float
    created_at: Annotated[datetime.datetime, Strict()] = field(
        default_factory=lambda: datetime.datetime.now(datetime.UTC)
    )
    updated_at: Annotated[datetime.datetime, Strict()] = field(
        default_factory=lambda: datetime.datetime.now(datetime.UTC)
    )

    @staticmethod
    def create(command: BotCreateCommand) -> "Bot":
        bot = Bot(
            user_id=command.user_id,
            credential_id=command.credential_id,
            name=command.name,
            symbol=command.symbol,
            strategy_type=command.strategy_type,
            is_active=command.is_active,
            allocated_capital=command.allocated_capital,
            stop_loss_pct=command.stop_loss_pct,
            take_profit_pct=command.take_profit_pct,
        )
        bot.validate()
        return bot

    @property
    def entity_id(self) -> BotId:
        return self.id

    def change_name(self, name: str) -> None:
        self.name = name
        self.touch()
        self.validate()

    def change_strategy_type(self, strategy_type: str) -> None:
        self.strategy_type = strategy_type
        self.touch()
        self.validate()

    def change_allocated_capital(self, allocated_capital: float) -> None:
        self.allocated_capital = allocated_capital
        self.touch()
        self.validate()

    def change_stop_loss_pct(self, stop_loss_pct: float) -> None:
        self.stop_loss_pct = stop_loss_pct
        self.touch()
        self.validate()

    def change_take_profit_pct(self, take_profit_pct: float) -> None:
        self.take_profit_pct = take_profit_pct
        self.touch()
        self.validate()

    def activate(self) -> None:
        self.is_active = True
        self.touch()

    def deactivate(self) -> None:
        self.is_active = False
        self.touch()

    def touch(self) -> None:
        self.updated_at = datetime.datetime.now(datetime.UTC)

    def validate(self):
        if self.strategy_type.upper() not in VALID_STRATEGY_TYPES:
            raise EntityValidationException(
                f"strategy_type '{self.strategy_type}' is not valid. "
                f"Choose from: {VALID_STRATEGY_TYPES}"
            )

        if not self.symbol or "/" not in self.symbol:
            raise EntityValidationException(
                "symbol must be a valid trading pair (e.g. BTC/USDT)."
            )
        base, quote = self.symbol.split("/", 1)
        if not base or not quote:
            raise EntityValidationException("symbol must contain BASE and QUOTE.")

        if self.allocated_capital <= 0:
            raise EntityValidationException(
                "allocated_capital must be greater than zero."
            )
        if not (0 <= self.stop_loss_pct <= 100):
            raise EntityValidationException(
                "stop_loss_pct must be a percentage between 0 and 100."
            )
        if self.take_profit_pct < 0:
            raise EntityValidationException("take_profit_pct must be positive.")

        self._validate(
            {
                "id": self.id,
                "user_id": self.user_id,
                "credential_id": self.credential_id,
                "name": self.name,
                "symbol": self.symbol,
                "strategy_type": self.strategy_type,
                "is_active": self.is_active,
                "allocated_capital": self.allocated_capital,
                "stop_loss_pct": self.stop_loss_pct,
                "take_profit_pct": self.take_profit_pct,
                "created_at": self.created_at,
                "updated_at": self.updated_at,
            }
        )
