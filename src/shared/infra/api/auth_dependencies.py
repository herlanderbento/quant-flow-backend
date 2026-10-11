from uuid import UUID

import jwt
from fastapi import Cookie, Depends
from sqlalchemy.ext.asyncio import AsyncSession

from account.domain.user import User
from account.infra.db.user_postgres_repository import UserPostgresRepository
from shared.domain.exceptions import UnauthorizedException
from shared.infra.db.config import settings
from shared.infra.db.database import get_db_session


class AuthContext:
    def __init__(self, user_id: UUID, user: User):
        self.user_id = user_id
        self.user = user


def decode_token(token: str, expected_type: str) -> UUID:
    try:
        payload = jwt.decode(
            token,
            settings.JWT_SECRET_KEY,
            algorithms=[settings.JWT_ALGORITHM],
        )
    except jwt.PyJWTError as exc:
        raise UnauthorizedException("Invalid or expired token") from exc

    if payload.get("type") != expected_type:
        raise UnauthorizedException("Invalid token type")

    return UUID(payload["sub"])


async def get_current_user(
    access_token: str | None = Cookie(default=None, alias=settings.ACCESS_TOKEN_COOKIE),
    session: AsyncSession = Depends(get_db_session),
) -> AuthContext:
    if not access_token:
        raise UnauthorizedException("Authentication required")

    user_id = decode_token(access_token, "access")
    user_repo = UserPostgresRepository(session)
    user = await user_repo.find_by_id(user_id)

    if user is None or not user.is_active:
        raise UnauthorizedException("User not authenticated")

    return AuthContext(user_id=user_id, user=user)


def require_authenticated(
    auth: AuthContext = Depends(get_current_user),
) -> AuthContext:
    return auth
