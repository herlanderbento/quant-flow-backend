from typing import Annotated
from uuid import UUID

from fastapi import APIRouter, Depends, Query, Response, status
from pydantic import BaseModel, StringConstraints

from account.application.use_cases.exchange_credential.create_exchange_credential import (
    CreateExchangeCredentialInput,
    CreateExchangeCredentialUseCase,
)
from account.application.use_cases.exchange_credential.delete_exchange_credential import (
    DeleteExchangeCredentialInput,
    DeleteExchangeCredentialUseCase,
)
from account.application.use_cases.exchange_credential.get_exchange_credentials_by_user import (
    GetExchangeCredentialsByUserInput,
    GetExchangeCredentialsByUserUseCase,
)
from account.domain.exchange_credential import ExchangeCredentialId
from account.domain.exchange_credential_repository import ExchangeCredentialFilter
from account.domain.user import UserId

from account.infra.api.exchange_credential.exchange_credential_presenter import (
    ExchangeCredentialCollectionPresenter,
    ExchangeCredentialPresenter,
)

from shared.infra.api.auth_dependencies import AuthContext, require_authenticated
from account.infra.api.exchange_credential.exchange_credential_dependencies import (
    get_create_exchange_credential_use_case,
    get_delete_exchange_credential_use_case,
    get_exchange_credentials_by_user_use_case,
)

router = APIRouter(prefix="/exchange-credentials", tags=["Exchange Credentials"])

NonEmptyStr = Annotated[str, StringConstraints(strip_whitespace=True, min_length=1)]


class CreateExchangeCredentialRequest(BaseModel):
    exchange_name: NonEmptyStr
    api_key: NonEmptyStr
    api_secret: NonEmptyStr
    is_testnet: bool


class UpdateExchangeCredentialRequest(BaseModel):
    exchange_name: NonEmptyStr | None = None
    api_key: NonEmptyStr | None = None
    api_secret: NonEmptyStr | None = None
    is_testnet: bool | None = None


@router.post(
    "", response_model=ExchangeCredentialPresenter, status_code=status.HTTP_201_CREATED
)
async def create_exchange_credential(
    request: CreateExchangeCredentialRequest,
    _auth: AuthContext = Depends(require_authenticated),
    use_case: CreateExchangeCredentialUseCase = Depends(
        get_create_exchange_credential_use_case
    ),
):
    output = await use_case.execute(
        CreateExchangeCredentialInput(
            user_id=UserId(value=_auth.user_id),
            exchange_name=request.exchange_name,
            api_key=request.api_key,
            api_secret=request.api_secret,
            is_testnet=request.is_testnet,
        )
    )
    return ExchangeCredentialPresenter.from_output(output)


@router.get(
    "/user",
    response_model=ExchangeCredentialCollectionPresenter,
    status_code=status.HTTP_200_OK,
)
async def get_exchange_credentials_by_user(
    page: int | None = Query(default=1, ge=1),
    per_page: int | None = Query(default=15, ge=1),
    sort: str | None = Query(default=None),
    sort_dir: str | None = Query(default=None),
    exchange_name: str | None = Query(default=None),
    is_testnet: bool | None = Query(default=None),
    is_active: bool | None = Query(default=None),
    _auth: AuthContext = Depends(require_authenticated),
    use_case: GetExchangeCredentialsByUserUseCase = Depends(
        get_exchange_credentials_by_user_use_case
    ),
):
    output = await use_case.execute(
        GetExchangeCredentialsByUserInput(
            user_id=UserId(value=_auth.user_id),
            page=page,
            per_page=per_page,
            sort=sort,
            sort_dir=sort_dir,
            filter=ExchangeCredentialFilter(
                exchange_name=exchange_name, is_testnet=is_testnet, is_active=is_active
            ),
        )
    )
    return ExchangeCredentialCollectionPresenter.from_output(output)


@router.delete("/{exchange_credential_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_exchange_credential(
    exchange_credential_id: UUID,
    _auth: AuthContext = Depends(require_authenticated),
    use_case: DeleteExchangeCredentialUseCase = Depends(
        get_delete_exchange_credential_use_case
    ),
):
    await use_case.execute(
        DeleteExchangeCredentialInput(
            id=ExchangeCredentialId(value=exchange_credential_id)
        )
    )
    return Response(status_code=status.HTTP_204_NO_CONTENT)
