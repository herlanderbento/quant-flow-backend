from dataclasses import dataclass
import datetime
from uuid import UUID

from account.domain.exchange_credential import ExchangeCredential


@dataclass(frozen=True)
class ExchangeCredentialOutput:
    id: UUID
    user_id: UUID
    exchange_name: str
    api_key: str
    api_secret_encrypted: str
    is_testnet: bool
    is_active: bool
    created_at: datetime.datetime
    updated_at: datetime.datetime | None

    @classmethod
    def from_entity(
        cls, user_api_key: ExchangeCredential
    ) -> "ExchangeCredentialOutput":
        return cls(
            id=user_api_key.id.value,
            user_id=user_api_key.user_id.value,
            exchange_name=user_api_key.exchange_name,
            api_key=user_api_key.api_key,
            api_secret_encrypted=user_api_key.api_secret_encrypted,
            is_testnet=user_api_key.is_testnet,
            is_active=user_api_key.is_active,
            created_at=user_api_key.created_at,
            updated_at=user_api_key.updated_at,
        )
