from unittest.mock import AsyncMock, MagicMock, patch
from uuid import uuid4

import pytest
from httpx import ASGITransport, AsyncClient

from account.application.use_cases.user.authenticate_user import (
    AuthenticateUserInput,
    AuthenticateUserUseCase,
)
from account.domain.user import User, UserId
from main import app
from shared.domain.exceptions import UnauthorizedException
from shared.infra.db.config import settings
from shared.infra.db.database import get_db_session
from shared.infra.token.jwt_token_generator import JwtTokenGenerator


def _user(active=True):
    return User(id=UserId(value=uuid4()), name="Ana", email="a@x.dev", password="h",
                is_active=active)


async def test_inactive_user_cannot_log_in():
    repo = AsyncMock()
    repo.find_by_email.return_value = _user(active=False)
    hasher = MagicMock()
    hasher.verify.return_value = True
    with pytest.raises(UnauthorizedException):
        await AuthenticateUserUseCase(repo, MagicMock(), hasher).execute(
            AuthenticateUserInput(email="a@x.dev", password="p"))


def test_access_tokens_are_short_lived_and_cookies_secure_by_default():
    assert settings.ACCESS_TOKEN_EXPIRE_MINUTES <= 60
    assert type(settings).model_fields["COOKIE_SECURE"].default is True


async def _refresh(cookie_value, user):
    async def fake_session():
        yield MagicMock()

    app.dependency_overrides[get_db_session] = fake_session
    repo = AsyncMock()
    repo.find_by_id.return_value = user
    try:
        with patch("account.infra.api.user.auth_controller.UserPostgresRepository",
                   return_value=repo):
            async with AsyncClient(transport=ASGITransport(app=app),
                                   base_url="https://test") as client:
                client.cookies.set(settings.REFRESH_TOKEN_COOKIE, cookie_value)
                return await client.post("/auth/refresh")
    finally:
        app.dependency_overrides.clear()


async def test_refresh_issues_new_tokens_from_refresh_cookie():
    user = _user()
    token = JwtTokenGenerator().generate({"sub": str(user.id.value), "type": "refresh"})
    response = await _refresh(token, user)
    assert response.status_code == 200
    assert settings.ACCESS_TOKEN_COOKIE in response.cookies


async def test_access_token_cannot_be_used_as_refresh_token():
    user = _user()
    token = JwtTokenGenerator().generate({"sub": str(user.id.value), "type": "access"})
    response = await _refresh(token, user)
    assert response.status_code == 401


async def test_inactive_user_cannot_refresh():
    user = _user(active=False)
    token = JwtTokenGenerator().generate({"sub": str(user.id.value), "type": "refresh"})
    response = await _refresh(token, user)
    assert response.status_code == 401
