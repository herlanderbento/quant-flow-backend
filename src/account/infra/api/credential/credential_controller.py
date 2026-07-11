from typing import Annotated
from uuid import UUID

from fastapi import APIRouter, Depends, Query, Response, status
from pydantic import BaseModel, StringConstraints

from account.application.use_cases.credential.create_credential import (
    CreateCredentialInput,
    CreateCredentialUseCase,
)
from account.application.use_cases.credential.delete_credential import (
    DeleteCredentialInput,
    DeleteCredentialUseCase,
)
from account.application.use_cases.credential.get_credentials_by_user import (
    GetCredentialsByUserInput,
    GetCredentialsByUserUseCase,
)
from account.domain.credential import CredentialId
from account.domain.credential_repository import CredentialFilter
from account.domain.user import UserId

from account.infra.api.credential.credential_presenter import (
    CredentialCollectionPresenter,
    CredentialPresenter,
)

from shared.infra.api.auth_dependencies import AuthContext, require_authenticated
from account.infra.api.credential.credential_dependencies import (
    get_create_credential_use_case,
    get_delete_credential_use_case,
    get_credentials_by_user_use_case,
)

router = APIRouter(prefix="/credentials", tags=["Credentials"])

NonEmptyStr = Annotated[str, StringConstraints(strip_whitespace=True, min_length=1)]


class CreateCredentialRequest(BaseModel):
    name: NonEmptyStr
    api_key: NonEmptyStr
    api_secret: NonEmptyStr
    is_testnet: bool


class UpdateCredentialRequest(BaseModel):
    name: NonEmptyStr | None = None
    api_key: NonEmptyStr | None = None
    api_secret: NonEmptyStr | None = None
    is_testnet: bool | None = None


@router.post(
    "", response_model=CredentialPresenter, status_code=status.HTTP_201_CREATED
)
async def create_credential(
    request: CreateCredentialRequest,
    _auth: AuthContext = Depends(require_authenticated),
    use_case: CreateCredentialUseCase = Depends(
        get_create_credential_use_case
    ),
):
    output = await use_case.execute(
        CreateCredentialInput(
            user_id=UserId(value=_auth.user_id),
            name=request.name,
            api_key=request.api_key,
            api_secret=request.api_secret,
            is_testnet=request.is_testnet,
        )
    )
    return CredentialPresenter.from_output(output)


@router.get(
    "/user",
    response_model=CredentialCollectionPresenter,
    status_code=status.HTTP_200_OK,
)
async def get_credentials_by_user(
    page: int | None = Query(default=1, ge=1),
    per_page: int | None = Query(default=15, ge=1),
    sort: str | None = Query(default=None),
    sort_dir: str | None = Query(default=None),
    name: str | None = Query(default=None),
    is_testnet: bool | None = Query(default=None),
    is_active: bool | None = Query(default=None),
    _auth: AuthContext = Depends(require_authenticated),
    use_case: GetCredentialsByUserUseCase = Depends(
        get_credentials_by_user_use_case
    ),
):
    output = await use_case.execute(
        GetCredentialsByUserInput(
            user_id=UserId(value=_auth.user_id),
            page=page,
            per_page=per_page,
            sort=sort,
            sort_dir=sort_dir,
            filter=CredentialFilter(
                name=name, is_testnet=is_testnet, is_active=is_active
            ),
        )
    )
    return CredentialCollectionPresenter.from_output(output)


@router.delete("/{credential_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_credential(
    credential_id: UUID,
    _auth: AuthContext = Depends(require_authenticated),
    use_case: DeleteCredentialUseCase = Depends(
        get_delete_credential_use_case
    ),
):
    await use_case.execute(
        DeleteCredentialInput(
            id=CredentialId(value=credential_id)
        )
    )
    return Response(status_code=status.HTTP_204_NO_CONTENT)
