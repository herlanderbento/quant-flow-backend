"""HTTP-level ownership checks: controllers must forward the authenticated user."""
from unittest.mock import AsyncMock, MagicMock
from uuid import uuid4

import pytest
from httpx import ASGITransport, AsyncClient

from account.application.use_cases.credential.delete_credential import (
    DeleteCredentialUseCase,
)
from account.application.use_cases.user.delete_user import DeleteUserUseCase
from account.application.use_cases.user.update_user import UpdateUserUseCase
from account.domain.credential import Credential
from account.domain.user import User, UserId
from account.infra.api.credential.credential_dependencies import (
    get_delete_credential_use_case,
)
from account.infra.api.user.user_dependencies import (
    get_delete_user_use_case,
    get_update_user_use_case,
)
from main import app
from shared.infra.api.auth_dependencies import AuthContext, require_authenticated

ATTACKER = uuid4()
VICTIM = uuid4()


@pytest.fixture
def client_as_attacker():
    user_repo = AsyncMock()
    user_repo.find_by_id.return_value = User(
        id=UserId(value=VICTIM), name="Victim", email="v@x.dev", password="h"
    )
    cred_repo = AsyncMock()
    cred_repo.find_by_id.return_value = Credential(
        user_id=UserId(value=VICTIM),
        name="BYBIT",
        api_key="k",
        api_secret="s",
        is_testnet=True,
        is_active=True,
    )

    app.dependency_overrides[require_authenticated] = lambda: AuthContext(
        user_id=ATTACKER, user=MagicMock()
    )
    app.dependency_overrides[get_update_user_use_case] = lambda: UpdateUserUseCase(
        user_repo, MagicMock()
    )
    app.dependency_overrides[get_delete_user_use_case] = lambda: DeleteUserUseCase(user_repo)
    app.dependency_overrides[get_delete_credential_use_case] = (
        lambda: DeleteCredentialUseCase(cred_repo)
    )
    yield AsyncClient(transport=ASGITransport(app=app), base_url="http://test"), user_repo, cred_repo
    app.dependency_overrides.clear()


async def test_patch_other_user_returns_403(client_as_attacker):
    client, user_repo, _ = client_as_attacker
    async with client:
        response = await client.patch(f"/users/{VICTIM}", json={"password": "pwned"})
    assert response.status_code == 403
    user_repo.update.assert_not_called()


async def test_delete_other_user_returns_403(client_as_attacker):
    client, user_repo, _ = client_as_attacker
    async with client:
        response = await client.delete(f"/users/{VICTIM}")
    assert response.status_code == 403
    user_repo.delete.assert_not_called()


async def test_delete_other_users_credential_returns_403(client_as_attacker):
    client, _, cred_repo = client_as_attacker
    async with client:
        response = await client.delete(f"/credentials/{uuid4()}")
    assert response.status_code == 403
    cred_repo.delete.assert_not_called()
