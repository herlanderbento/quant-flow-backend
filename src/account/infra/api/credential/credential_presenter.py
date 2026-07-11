from datetime import datetime
from uuid import UUID
from pydantic import BaseModel, ConfigDict

from account.application.use_cases.credential.common.credential_output import (
    CredentialOutput,
)
from account.application.use_cases.credential.list_credentials import (
    ListCredentialsOutput,
)
from shared.infra.api.presenter import CollectionPresenter, meta_from_output


class CredentialPresenter(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: UUID
    user_id: UUID
    name: str
    api_key: str
    api_secret: str
    is_testnet: bool
    is_active: bool
    created_at: datetime
    updated_at: datetime | None

    @classmethod
    def from_output(cls, output: CredentialOutput) -> "CredentialPresenter":
        return cls(
            id=output.id,
            user_id=output.user_id,
            name=output.name,
            api_key=output.api_key,
            api_secret=output.api_secret,
            is_testnet=output.is_testnet,
            is_active=output.is_active,
            created_at=output.created_at,
            updated_at=output.updated_at,
        )


class CredentialCollectionPresenter(CollectionPresenter[CredentialPresenter]):
    @classmethod
    def from_output(
        cls, output: ListCredentialsOutput
    ) -> "CredentialCollectionPresenter":
        return cls(
            data=[CredentialPresenter.from_output(item) for item in output.items],
            meta=meta_from_output(output),
        )
