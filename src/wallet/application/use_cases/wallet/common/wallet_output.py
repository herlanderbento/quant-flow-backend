from dataclasses import dataclass
import datetime
from uuid import UUID

from wallet.domain.wallet import Wallet


@dataclass(frozen=True)
class WalletOutput:
    id: UUID
    user_id: UUID
    asset: str
    free_balance: float
    locked_balance: float
    updated_at: datetime.datetime

    @classmethod
    def from_entity(cls, wallet: Wallet) -> "WalletOutput":
        return cls(
            id=wallet.id.value,
            user_id=wallet.user_id.value,
            asset=wallet.asset,
            free_balance=wallet.free_balance,
            locked_balance=wallet.locked_balance,
            updated_at=wallet.updated_at,
        )
