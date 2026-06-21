from fastapi import APIRouter, Depends, Query, status
from pydantic import BaseModel
from sqlalchemy.ext.asyncio import AsyncSession
from account.application.use_cases.exchange_credential.create_exchange_credential import (
    CreateExchangeCredentialInput,
    CreateExchangeCredentialUseCase,
)
from account.application.use_cases.exchange_credential.get_exchange_credentials_by_user import (
    GetExchangeCredentialsByUserInput,
    GetExchangeCredentialsByUserUseCase,
)
from account.domain.exchange_credential_repository import ExchangeCredentialFilter
from account.infra.api.exchange_credential.exchange_credential_presenter import (
    ExchangeCredentialCollectionPresenter,
    ExchangeCredentialPresenter,
)
from account.infra.db.exchange_credential_postgres_repository import (
    ExchangeCredentialPostgresRepository,
)
from account.infra.db.user_postgres_repository import UserPostgresRepository
from shared.infra.api.auth_dependencies import AuthContext, require_authenticated
from shared.infra.cryptography.bcrypt_hasher import BcryptHasher
from shared.infra.db.database import get_db_session

router = APIRouter(prefix="/exchange-credentials", tags=["Exchange Credentials"])


class CreateExchangeCredentialRequest(BaseModel):
    exchange_name: str
    api_key: str
    api_secret_encrypted: str
    is_testnet: bool


class UpdateExchangeCredentialRequest(BaseModel):
    exchange_name: str | None = None
    api_key: str | None = None
    api_secret_encrypted: str | None = None
    is_testnet: bool | None = None


@router.post(
    "", response_model=ExchangeCredentialPresenter, status_code=status.HTTP_201_CREATED
)
async def create_exchange_credential(
    request: CreateExchangeCredentialRequest,
    session: AsyncSession = Depends(get_db_session),
    _auth: AuthContext = Depends(require_authenticated),
):
    exchange_credential_repo = ExchangeCredentialPostgresRepository(session)
    user_repo = UserPostgresRepository(session)
    cryptography = BcryptHasher()

    use_case = CreateExchangeCredentialUseCase(
        exchange_credential_repo, cryptography, user_repo
    )

    output = await use_case.execute(
        CreateExchangeCredentialInput(
            user_id=_auth.user_id,
            exchange_name=request.exchange_name,
            api_key=request.api_key,
            api_secret_encrypted=request.api_secret_encrypted,
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
    session: AsyncSession = Depends(get_db_session),
    _auth: AuthContext = Depends(require_authenticated),
):
    exchange_credential_repo = ExchangeCredentialPostgresRepository(session)
    user_repo = UserPostgresRepository(session)
    use_case = GetExchangeCredentialsByUserUseCase(exchange_credential_repo, user_repo)

    output = await use_case.execute(
        GetExchangeCredentialsByUserInput(
            user_id=_auth.user_id,
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
