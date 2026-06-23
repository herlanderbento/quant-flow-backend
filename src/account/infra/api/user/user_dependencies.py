from fastapi import Depends
from sqlalchemy.ext.asyncio import AsyncSession

from account.application.use_cases.user.create_user import CreateUserUseCase
from account.application.use_cases.user.delete_user import DeleteUserUseCase
from account.application.use_cases.user.get_user import GetUserUseCase
from account.application.use_cases.user.list_users import ListUsersUseCase
from account.application.use_cases.user.update_user import UpdateUserUseCase
from account.domain.user_repository import IUserRepository

from account.infra.db.user_postgres_repository import UserPostgresRepository
from shared.application.cryptography import IPasswordHasher
from shared.infra.api.dependencies import get_bcrypt_hasher
from shared.infra.db.database import get_db_session


# Dependency to get repository
def get_user_repository(
    session: AsyncSession = Depends(get_db_session),
) -> IUserRepository:
    return UserPostgresRepository(session)


# Dependency to get use case
def get_create_user_use_case(
    user_repo: IUserRepository = Depends(get_user_repository),
    password_hasher: IPasswordHasher = Depends(get_bcrypt_hasher),
) -> CreateUserUseCase:
    return CreateUserUseCase(user_repo, password_hasher)

def get_delete_user_use_case(
    user_repo: IUserRepository = Depends(get_user_repository),
) -> DeleteUserUseCase:
    return DeleteUserUseCase(user_repo)

def get_get_user_use_case(
    user_repo: IUserRepository = Depends(get_user_repository),
) -> GetUserUseCase:
    return GetUserUseCase(user_repo)

def get_list_users_use_case(
    user_repo: IUserRepository = Depends(get_user_repository),
) -> ListUsersUseCase:
    return ListUsersUseCase(user_repo)

def get_update_user_use_case(
    user_repo: IUserRepository = Depends(get_user_repository),
    password_hasher: IPasswordHasher = Depends(get_bcrypt_hasher),
) -> UpdateUserUseCase:
    return UpdateUserUseCase(user_repo, password_hasher)
