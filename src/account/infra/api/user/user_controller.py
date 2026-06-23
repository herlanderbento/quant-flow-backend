from uuid import UUID
from fastapi import APIRouter, Depends, Query, Response, status
from pydantic import BaseModel, EmailStr
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
from account.infra.api.user.user_dependencies import (
    get_create_user_use_case,
    get_delete_user_use_case,
    get_get_user_use_case,
    get_list_users_use_case,
    get_update_user_use_case,
)
from account.infra.api.user.user_presenter import (
    UserCollectionPresenter,
    UserPresenter,
)
from shared.infra.api.auth_dependencies import AuthContext, require_authenticated


router = APIRouter(prefix="/users", tags=["Users"])


class CreateUserRequest(BaseModel):
    name: str
    email: EmailStr
    password: str


class UpdateUserRequest(BaseModel):
    name: str | None = None
    email: EmailStr | None = None
    password: str | None = None
    is_active: bool | None = None


@router.post("", response_model=UserPresenter, status_code=status.HTTP_201_CREATED)
async def create_user(
    request: CreateUserRequest,
    use_case: CreateUserUseCase = Depends(get_create_user_use_case),
):
    output = await use_case.execute(
        CreateUserInput(
            name=request.name,
            email=str(request.email),
            password=request.password,
        )
    )
    return UserPresenter.from_output(output)


@router.get("/{user_id}", response_model=UserPresenter, status_code=status.HTTP_200_OK)
async def get_user(
    user_id: UUID,
    _auth: AuthContext = Depends(require_authenticated),
    use_case: GetUserUseCase = Depends(get_get_user_use_case),
):
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
    _auth: AuthContext = Depends(require_authenticated),
    use_case: ListUsersUseCase = Depends(get_list_users_use_case),
):

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
    request: UpdateUserRequest,
    use_case: UpdateUserUseCase = Depends(get_update_user_use_case),
    _auth: AuthContext = Depends(require_authenticated),
):
    payload = request.model_dump(exclude_none=True)
    if "email" in payload:
        payload["email"] = str(payload["email"])

    output = await use_case.execute(UpdateUserInput(id=user_id, **payload))
    return UserPresenter.from_output(output)


@router.delete("/{user_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_user(
    user_id: UUID,
    use_case: DeleteUserUseCase = Depends(get_delete_user_use_case),
    _auth: AuthContext = Depends(require_authenticated),
):

    await use_case.execute(DeleteUserInput(user_id=user_id))

    return Response(status_code=status.HTTP_204_NO_CONTENT)
