from uuid import UUID


from fastapi import APIRouter, Depends, Query, Response, status

from pydantic import BaseModel, EmailStr

from sqlalchemy.ext.asyncio import AsyncSession


from account.application.use_cases.user.create_user import (
    CreateUserInput,
    CreateUserUseCase,
)

from account.application.use_cases.user.delete_user import (
    DeleteUserInput,
    DeleteUserUseCase,
)

from account.application.use_cases.user.get_user import GetUserInput, GetUserUseCase

from account.application.use_cases.user.list_users import (
    ListUsersInput,
    ListUsersUseCase,
)

from account.application.use_cases.user.update_user import (
    UpdateUserInput,
    UpdateUserUseCase,
)

from account.domain.user import UserId

from account.domain.user_repository import UserFilter

from account.infra.api.user_presenter import UserCollectionPresenter, UserPresenter

from account.infra.db.user_postgres_repository import UserPostgresRepository

from shared.infra.api.auth_dependencies import AuthContext, require_authenticated

from shared.infra.cryptography.bcrypt_hasher import BcryptHasher

from shared.infra.db.database import get_db_session


router = APIRouter(prefix="/users", tags=["Users"])


@router.post("", response_model=UserPresenter, status_code=status.HTTP_201_CREATED)
async def create_user(
    request: BaseModel,
    session: AsyncSession = Depends(get_db_session),
):

    user_repo = UserPostgresRepository(session)

    cryptography = BcryptHasher()

    use_case = CreateUserUseCase(user_repo, cryptography)

    output = await use_case.execute(
        CreateUserInput(
            **request.model_dump(),
        )
    )

    return UserPresenter.from_output(output)


@router.get("/{user_id}", response_model=UserPresenter, status_code=status.HTTP_200_OK)
async def get_user(
    user_id: UUID,
    session: AsyncSession = Depends(get_db_session),
    _auth: AuthContext = Depends(require_authenticated),
):

    user_repo = UserPostgresRepository(session)

    use_case = GetUserUseCase(user_repo)

    output = await use_case.execute(GetUserInput(user_id=UserId(value=user_id)))

    return UserPresenter.from_output(output)


@router.get("", response_model=UserCollectionPresenter, status_code=status.HTTP_200_OK)
async def list_users(
    page: int | None = Query(default=1, ge=1),
    per_page: int | None = Query(default=15, ge=1),
    sort: str | None = Query(default=None),
    sort_dir: str | None = Query(default=None),
    name: str | None = Query(default=None),
    email: str | None = Query(default=None),
    is_active: bool | None = Query(default=None),
    session: AsyncSession = Depends(get_db_session),
    _auth: AuthContext = Depends(require_authenticated),
):

    user_repo = UserPostgresRepository(session)

    use_case = ListUsersUseCase(user_repo)

    search_input = ListUsersInput(
        page=page,
        per_page=per_page,
        sort=sort,
        sort_dir=sort_dir,
        filter=UserFilter(
            name=name,
            email=email,
            is_active=is_active,
        ),
    )

    output = await use_case.execute(search_input)

    return UserCollectionPresenter.from_output(output)


@router.patch(
    "/{user_id}", response_model=UserPresenter, status_code=status.HTTP_200_OK
)
async def update_user(
    user_id: UUID,
    request: BaseModel,
    session: AsyncSession = Depends(get_db_session),
    _auth: AuthContext = Depends(require_authenticated),
):

    user_repo = UserPostgresRepository(session)

    cryptography = BcryptHasher()

    use_case = UpdateUserUseCase(user_repo, cryptography)

    output = await use_case.execute(
        UpdateUserInput(id=user_id, **request.model_dump(exclude_none=True))
    )

    return UserPresenter.from_output(output)


@router.delete("/{user_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_user(
    user_id: UUID,
    session: AsyncSession = Depends(get_db_session),
    _auth: AuthContext = Depends(require_authenticated),
):

    user_repo = UserPostgresRepository(session)

    use_case = DeleteUserUseCase(user_repo)

    await use_case.execute(DeleteUserInput(user_id=user_id))

    return Response(status_code=status.HTTP_204_NO_CONTENT)
