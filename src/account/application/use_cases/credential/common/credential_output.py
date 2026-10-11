from dataclasses import dataclass
import datetime
from uuid import UUID

from account.domain.credential import Credential


@dataclass(frozen=True)
class CredentialOutput:
    id: UUID
    user_id: UUID
    name: str
    # Masked: only the last characters are ever returned.
    api_key: str
    is_testnet: bool
    is_active: bool
    created_at: datetime.datetime
    updated_at: datetime.datetime | None

    @classmethod
    def from_entity(
        cls, credential: Credential
    ) -> "CredentialOutput":
        return cls(
            id=credential.id.value,
            user_id=credential.user_id.value,
            name=credential.name,
            api_key="*" * 12 + (credential.api_key_hint or ""),
            is_testnet=credential.is_testnet,
            is_active=credential.is_active,
            created_at=credential.created_at,
            updated_at=credential.updated_at,
        )
