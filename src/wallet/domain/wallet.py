from dataclasses import dataclass, field
import datetime
from datetime import timezone
from typing import Annotated

from pydantic import Strict

from account.domain.user import UserId
from shared.domain.entity import AggregateRoot
from shared.domain.value_objects import Uuid


class WalletId(Uuid):
    pass


@dataclass(slots=True, kw_only=True)
class Wallet(AggregateRoot):
    id: WalletId = field(default_factory=WalletId)
    user_id: UserId
    asset: str
    free_balance: float
    locked_balance: float
    updated_at: Annotated[datetime.datetime, Strict()] = field(
        default_factory=lambda: datetime.datetime.now(timezone.utc)
    )

    @property
    def entity_id(self) -> WalletId:
        return self.id

    def update_balances(self, free_balance: float, locked_balance: float) -> None:
        self.free_balance = free_balance
        self.locked_balance = locked_balance
        self.updated_at = datetime.datetime.now(timezone.utc)
        self.validate()

    def validate(self) -> None:
        self._validate(
            {
                "id": self.id,
                "user_id": self.user_id,
                "asset": self.asset,
                "free_balance": self.free_balance,
                "locked_balance": self.locked_balance,
                "updated_at": self.updated_at,
            }
        )
