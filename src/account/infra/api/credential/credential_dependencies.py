from fastapi import Depends
from sqlalchemy.ext.asyncio import AsyncSession

from account.application.use_cases.credential.create_credential import (
    CreateCredentialUseCase,
)
from account.application.use_cases.credential.delete_credential import (
    DeleteCredentialUseCase,
)
from account.application.use_cases.credential.get_credentials_by_user import (
    GetCredentialsByUserUseCase,
)
from account.domain.credential_repository import ICredentialRepository
from account.domain.user_repository import IUserRepository
from account.infra.api.user.user_dependencies import get_user_repository
from account.infra.db.credential_postgres_repository import (
    CredentialPostgresRepository,
)
from shared.application.cryptography import IEncryption
from shared.infra.api.dependencies import get_encryption
from shared.infra.db.database import get_db_session


# Dependency to get repository
def get_credential_repository(
    session: AsyncSession = Depends(get_db_session),
) -> ICredentialRepository:
    return CredentialPostgresRepository(session)


# Dependency to get use case
def get_create_credential_use_case(
    repo: ICredentialRepository = Depends(
        get_credential_repository
    ),
    user_repo: IUserRepository = Depends(get_user_repository),
    encryption: IEncryption = Depends(get_encryption),
) -> CreateCredentialUseCase:
    return CreateCredentialUseCase(repo, encryption, user_repo)


def get_credentials_by_user_use_case(
    repo: ICredentialRepository = Depends(
        get_credential_repository
    ),
    user_repo: IUserRepository = Depends(get_user_repository),
) -> GetCredentialsByUserUseCase:
    return GetCredentialsByUserUseCase(repo, user_repo)


def get_delete_credential_use_case(
    repo: ICredentialRepository = Depends(
        get_credential_repository
    ),
) -> DeleteCredentialUseCase:
    return DeleteCredentialUseCase(repo)
