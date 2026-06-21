from datetime import datetime
from uuid import UUID
from pydantic import BaseModel, ConfigDict

from account.application.use_cases.exchange_credential.common.exchange_credential_output import (
    ExchangeCredentialOutput,
)
from account.domain.exchange_credential_repository import ExchangeCredentialSearchOutput


class ExchangeCredentialPresenter(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: UUID
    user_id: UUID
    exchange_name: str
    api_key: str
    api_secret_encrypted: str
    is_testnet: bool
    is_active: bool
    created_at: datetime
    updated_at: datetime | None

    @classmethod
    def from_output(
        cls, output: ExchangeCredentialOutput
    ) -> "ExchangeCredentialPresenter":
        return cls(
            id=output.id,
            user_id=output.user_id,
            exchange_name=output.exchange_name,
            api_key=output.api_key,
            api_secret_encrypted=output.api_secret_encrypted,
            is_testnet=output.is_testnet,
            is_active=output.is_active,
            created_at=output.created_at,
            updated_at=output.updated_at,
        )


class MetaPresenter(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    total: int
    current_page: int
    per_page: int
    last_page: int


class ExchangeCredentialCollectionPresenter(BaseModel):
    data: list[ExchangeCredentialPresenter]
    meta: MetaPresenter

    @classmethod
    def from_output(
        cls, output: ExchangeCredentialSearchOutput
    ) -> "ExchangeCredentialCollectionPresenter":
        return cls(
            data=[
                ExchangeCredentialPresenter.from_output(item) for item in output.items
            ],
            meta=MetaPresenter(
                total=output.total,
                current_page=output.current_page,
                per_page=output.per_page,
                last_page=output.last_page,
            ),
        )
