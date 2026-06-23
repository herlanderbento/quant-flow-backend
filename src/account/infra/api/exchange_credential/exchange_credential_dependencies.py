from fastapi import Depends
from sqlalchemy.ext.asyncio import AsyncSession

from account.application.use_cases.exchange_credential.create_exchange_credential import (
    CreateExchangeCredentialUseCase,
)
from account.application.use_cases.exchange_credential.delete_exchange_credential import (
    DeleteExchangeCredentialUseCase,
)
from account.application.use_cases.exchange_credential.get_exchange_credentials_by_user import (
    GetExchangeCredentialsByUserUseCase,
)
from account.domain.exchange_credential_repository import IExchangeCredentialRepository
from account.domain.user_repository import IUserRepository
from account.infra.api.user.user_dependencies import get_user_repository
from account.infra.db.exchange_credential_postgres_repository import (
    ExchangeCredentialPostgresRepository,
)
from shared.application.cryptography import IEncryption
from shared.infra.api.dependencies import get_encryption
from shared.infra.db.database import get_db_session


# Dependency to get repository
def get_exchange_credential_repository(
    session: AsyncSession = Depends(get_db_session),
) -> IExchangeCredentialRepository:
    return ExchangeCredentialPostgresRepository(session)


# Dependency to get use case
def get_create_exchange_credential_use_case(
    exchange_repo: IExchangeCredentialRepository = Depends(
        get_exchange_credential_repository
    ),
    user_repo: IUserRepository = Depends(get_user_repository),
    encryption: IEncryption = Depends(get_encryption),
) -> CreateExchangeCredentialUseCase:
    return CreateExchangeCredentialUseCase(exchange_repo, encryption, user_repo)


def get_exchange_credentials_by_user_use_case(
    exchange_repo: IExchangeCredentialRepository = Depends(
        get_exchange_credential_repository
    ),
    user_repo: IUserRepository = Depends(get_user_repository),
) -> GetExchangeCredentialsByUserUseCase:
    return GetExchangeCredentialsByUserUseCase(exchange_repo, user_repo)


def get_delete_exchange_credential_use_case(
    exchange_repo: IExchangeCredentialRepository = Depends(
        get_exchange_credential_repository
    ),
) -> DeleteExchangeCredentialUseCase:
    return DeleteExchangeCredentialUseCase(exchange_repo)
