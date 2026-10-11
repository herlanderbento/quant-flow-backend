from unittest.mock import AsyncMock, MagicMock
from uuid import uuid4

import pytest

from account.application.use_cases.credential.delete_credential import (
    DeleteCredentialInput,
    DeleteCredentialUseCase,
)
from account.application.use_cases.user.delete_user import (
    DeleteUserInput,
    DeleteUserUseCase,
)
from account.application.use_cases.user.get_user import GetUserInput, GetUserUseCase
from account.application.use_cases.user.update_user import (
    UpdateUserInput,
    UpdateUserUseCase,
)
from account.domain.credential import Credential
from account.domain.user import User, UserId
from shared.domain.exceptions import ForbiddenException
from tests.sample_data import SAMPLE_EMAIL, SAMPLE_NAME


def _user(user_id) -> User:
    return User(id=UserId(value=user_id), name=SAMPLE_NAME, email=SAMPLE_EMAIL, password="h")


def _credential(owner_id) -> Credential:
    return Credential(
        user_id=UserId(value=owner_id),
        name="BYBIT",
        api_key="k",
        api_secret="s",
        is_testnet=True,
        is_active=True,
    )


class TestUserOwnership:
    async def test_get_other_user_is_forbidden(self):
        repo = AsyncMock()
        victim, attacker = uuid4(), uuid4()
        repo.find_by_id.return_value = _user(victim)

        with pytest.raises(ForbiddenException):
            await GetUserUseCase(repo).execute(
                GetUserInput(user_id=UserId(value=victim), requester_id=UserId(value=attacker))
            )

    async def test_get_self_is_allowed(self):
        repo = AsyncMock()
        me = uuid4()
        repo.find_by_id.return_value = _user(me)

        output = await GetUserUseCase(repo).execute(
            GetUserInput(user_id=UserId(value=me), requester_id=UserId(value=me))
        )
        assert output.id == me

    async def test_update_other_user_password_is_forbidden(self):
        repo = AsyncMock()
        hasher = MagicMock()
        victim, attacker = uuid4(), uuid4()
        repo.find_by_id.return_value = _user(victim)

        with pytest.raises(ForbiddenException):
            await UpdateUserUseCase(repo, hasher).execute(
                UpdateUserInput(id=victim, requester_id=attacker, password="pwned")
            )

        hasher.hash.assert_not_called()
        repo.update.assert_not_called()

    async def test_update_self_is_allowed(self):
        repo = AsyncMock()
        me = uuid4()
        repo.find_by_id.return_value = _user(me)

        await UpdateUserUseCase(repo, MagicMock()).execute(
            UpdateUserInput(id=me, requester_id=me, name="Novo")
        )
        repo.update.assert_awaited_once()

    async def test_delete_other_user_is_forbidden(self):
        repo = AsyncMock()
        victim, attacker = uuid4(), uuid4()
        repo.find_by_id.return_value = _user(victim)

        with pytest.raises(ForbiddenException):
            await DeleteUserUseCase(repo).execute(
                DeleteUserInput(user_id=victim, requester_id=attacker)
            )
        repo.delete.assert_not_called()


class TestCredentialOwnership:
    async def test_delete_other_users_credential_is_forbidden(self):
        repo = AsyncMock()
        victim, attacker = uuid4(), uuid4()
        credential = _credential(victim)
        repo.find_by_id.return_value = credential

        with pytest.raises(ForbiddenException):
            await DeleteCredentialUseCase(repo).execute(
                DeleteCredentialInput(id=credential.id, user_id=UserId(value=attacker))
            )
        repo.delete.assert_not_called()

    async def test_delete_own_credential_is_allowed(self):
        repo = AsyncMock()
        me = uuid4()
        credential = _credential(me)
        repo.find_by_id.return_value = credential

        await DeleteCredentialUseCase(repo).execute(
            DeleteCredentialInput(id=credential.id, user_id=UserId(value=me))
        )
        repo.delete.assert_awaited_once_with(credential.id.value)
