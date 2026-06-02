from dataclasses import dataclass, field
import datetime
from typing import Annotated

from pydantic import Strict

from shared.domain.entity import AggregateRoot
from shared.domain.value_objects import Uuid
from account.domain.user import UserId


@dataclass
class ExchangeCredentialCreateCommand:
    user_id: UserId
    exchange_name: str
    api_key: str
    api_secret_encrypted: str
    is_testnet: bool


class ExchangeCredentialId(Uuid):
    pass


@dataclass(slots=True, kw_only=True)
class ExchangeCredential(AggregateRoot):
    id: ExchangeCredentialId = field(default_factory=ExchangeCredentialId)
    user_id: UserId
    exchange_name: str
    api_key: str
    api_secret_encrypted: str
    is_testnet: bool
    is_active: bool
    created_at: Annotated[datetime.datetime, Strict()] = field(
        default_factory=lambda: datetime.datetime.now(datetime.UTC)
    )
    updated_at: Annotated[datetime.datetime, Strict()] = field(
        default_factory=lambda: datetime.datetime.now(datetime.UTC)
    )

    @staticmethod
    def create(command: ExchangeCredentialCreateCommand) -> "ExchangeCredential":
        return ExchangeCredential(
            user_id=command.user_id,
            exchange_name=command.exchange_name,
            api_key=command.api_key,
            api_secret_encrypted=command.api_secret_encrypted,
            is_testnet=command.is_testnet,
            is_active=True,
        ) 

    @property
    def entity_id(self) -> ExchangeCredentialId:
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
                "exchange_name": self.exchange_name,
                "api_key": self.api_key,
                "api_secret_encrypted": self.api_secret_encrypted,
                "is_testnet": self.is_testnet,
                "is_active": self.is_active,
                "created_at": self.created_at,
                "updated_at": self.updated_at,
            }
        )
