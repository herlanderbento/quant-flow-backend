from dataclasses import dataclass
from uuid import UUID
import datetime

from account.domain.user import User


@dataclass(frozen=True)
class UserOutput:
    id: UUID
    name: str
    email: str
    is_active: bool | None
    created_at: datetime.datetime
    updated_at: datetime.datetime | None

    @classmethod
    def from_entity(cls, user: User) -> "UserOutput":
        return cls(
            id=user.id.value,
            name=user.name,
            email=user.email,
            is_active=user.is_active,
            created_at=user.created_at,
            updated_at=user.updated_at,
        )
