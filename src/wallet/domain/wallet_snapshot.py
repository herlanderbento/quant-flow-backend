from dataclasses import dataclass, field
import datetime
from datetime import timezone
from typing import Annotated

from pydantic import Strict

from account.domain.user import UserId
from shared.domain.entity import AggregateRoot
from shared.domain.value_objects import Uuid


class WalletSnapshotId(Uuid):
    pass


@dataclass(slots=True, kw_only=True)
class WalletSnapshot(AggregateRoot):
    id: WalletSnapshotId = field(default_factory=WalletSnapshotId)
    user_id: UserId
    total_equity_usdt: float
    snapshot_date: datetime.date
    created_at: Annotated[datetime.datetime, Strict()] = field(
        default_factory=lambda: datetime.datetime.now(timezone.utc)
    )

    @property
    def entity_id(self) -> WalletSnapshotId:
        return self.id

    def validate(self) -> None:
        self._validate(
            {
                "id": self.id,
                "user_id": self.user_id,
                "total_equity_usdt": self.total_equity_usdt,
                "snapshot_date": self.snapshot_date,
                "created_at": self.created_at,
            }
        )
