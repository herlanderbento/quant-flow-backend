from fastapi import APIRouter, Cookie, Depends, Response, status
from fastapi.responses import JSONResponse
from pydantic import BaseModel, EmailStr
from sqlalchemy.ext.asyncio import AsyncSession

from account.application.use_cases.user.authenticate_user import (
    AuthenticateUserInput,
    AuthenticateUserUseCase,
)
from account.infra.api.user.user_presenter import UserPresenter
from account.infra.db.user_postgres_repository import UserPostgresRepository
from shared.domain.exceptions import UnauthorizedException
from shared.infra.api.auth_cookies import clear_auth_cookies, set_auth_cookies
from shared.infra.api.auth_dependencies import decode_token
from shared.infra.db.config import settings
from shared.infra.cryptography.bcrypt_hasher import BcryptHasher
from shared.infra.db.database import get_db_session
from shared.infra.token.jwt_token_generator import JwtTokenGenerator

router = APIRouter(prefix="/auth", tags=["Auth"])


class LoginRequest(BaseModel):
    email: EmailStr
    password: str


@router.post("/login", response_model=UserPresenter, status_code=status.HTTP_200_OK)
async def login(
    request: LoginRequest,
    session: AsyncSession = Depends(get_db_session),
):
    user_repo = UserPostgresRepository(session)
    use_case = AuthenticateUserUseCase(
        user_repo,
        JwtTokenGenerator(),
        BcryptHasher(),
    )

    output = await use_case.execute(
        AuthenticateUserInput(
            email=str(request.email),
            password=request.password,
        )
    )

    response = JSONResponse(
        status_code=status.HTTP_200_OK,
        content=UserPresenter.from_output(output.user).model_dump(mode="json"),
    )
    set_auth_cookies(response, output.access_token, output.refresh_token)
    return response


@router.post("/refresh", response_model=UserPresenter, status_code=status.HTTP_200_OK)
async def refresh(
    refresh_token: str | None = Cookie(default=None, alias=settings.REFRESH_TOKEN_COOKIE),
    session: AsyncSession = Depends(get_db_session),
):
    if not refresh_token:
        raise UnauthorizedException("Authentication required")

    user_repo = UserPostgresRepository(session)
    user = await user_repo.find_by_id(decode_token(refresh_token, "refresh"))
    if user is None:
        raise UnauthorizedException("User not authenticated")

    use_case = AuthenticateUserUseCase(user_repo, JwtTokenGenerator(), BcryptHasher())
    output = use_case.issue_tokens(user)

    response = JSONResponse(
        status_code=status.HTTP_200_OK,
        content=UserPresenter.from_output(output.user).model_dump(mode="json"),
    )
    set_auth_cookies(response, output.access_token, output.refresh_token)
    return response


@router.post("/logout", status_code=status.HTTP_204_NO_CONTENT)
async def logout():
    response = Response(status_code=status.HTTP_204_NO_CONTENT)
    clear_auth_cookies(response)
    return response
