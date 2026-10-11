from dataclasses import dataclass, field
import datetime
from typing import Annotated

from pydantic import Strict

from shared.domain.entity import AggregateRoot
from shared.domain.value_objects import Uuid
from account.domain.user import UserId


@dataclass
class CredentialCreateCommand:
    user_id: UserId
    name: str
    api_key: str
    api_secret: str
    is_testnet: bool
    api_key_hint: str | None = None


class CredentialId(Uuid):
    pass


@dataclass(slots=True, kw_only=True)
class Credential(AggregateRoot):
    id: CredentialId = field(default_factory=CredentialId)
    user_id: UserId
    name: str
    api_key: str  # encrypted at rest
    api_secret: str  # encrypted at rest
    is_testnet: bool
    is_active: bool
    # Last characters of the plaintext key, for display only.
    api_key_hint: str | None = None
    created_at: Annotated[datetime.datetime, Strict()] = field(
        default_factory=lambda: datetime.datetime.now(datetime.UTC)
    )
    updated_at: Annotated[datetime.datetime, Strict()] = field(
        default_factory=lambda: datetime.datetime.now(datetime.UTC)
    )

    @staticmethod
    def create(command: CredentialCreateCommand) -> "Credential":
        return Credential(
            user_id=command.user_id,
            name=command.name,
            api_key=command.api_key,
            api_secret=command.api_secret,
            is_testnet=command.is_testnet,
            is_active=True,
            api_key_hint=command.api_key_hint,
        ) 

    @property
    def entity_id(self) -> CredentialId:
        return self.id

    def activate(self):
        self.is_active = True
        self.touch()

    def deactivate(self):
        self.is_active = False
        self.touch()

    def touch(self):
        self.updated_at = datetime.datetime.now(datetime.UTC)

    def validate(self):
        self._validate(
            {
                "id": self.id,
                "user_id": self.user_id,
                "name": self.name,
                "api_key": self.api_key,
                "api_secret": self.api_secret,
                "is_testnet": self.is_testnet,
                "is_active": self.is_active,
                "created_at": self.created_at,
                "updated_at": self.updated_at,
            }
        )
