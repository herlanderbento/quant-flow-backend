from unittest.mock import MagicMock, patch

import pytest

from account.application.use_cases.create_user import CreateUserInput, CreateUserUseCase
from account.domain.user import User, UserCreateCommand
from shared.domain.exceptions import ConflictException
from tests.sample_data import SAMPLE_EMAIL, SAMPLE_NAME, SAMPLE_PLAIN_TEXT

HASHED_VALUE = "hashed-secret"


def _create_user_input(**overrides) -> CreateUserInput:
    data = {
        "name": SAMPLE_NAME,
        "email": SAMPLE_EMAIL,
        "password": SAMPLE_PLAIN_TEXT,
        "is_active": True,
    }
    data.update(overrides)
    return CreateUserInput(**data)


class TestCreateUserUseCase:
    def test_creates_user_when_email_is_available(self):
        repository = MagicMock()
        repository.find_by_email.return_value = None

        cryptography = MagicMock()
        cryptography.hash.return_value = HASHED_VALUE

        use_case = CreateUserUseCase(repository, cryptography)
        input_dto = _create_user_input()

        with patch.object(User, "create", wraps=User.create) as create_user:
            output = use_case.execute(input_dto)

        repository.find_by_email.assert_called_once_with(SAMPLE_EMAIL)
        cryptography.hash.assert_called_once_with(SAMPLE_PLAIN_TEXT)
        repository.insert.assert_called_once()

        command: UserCreateCommand = create_user.call_args[0][0]
        assert command.name == SAMPLE_NAME
        assert command.email == SAMPLE_EMAIL
        assert command.password == HASHED_VALUE
        assert command.is_active is True

        inserted_user: User = repository.insert.call_args[0][0]
        assert inserted_user.name == SAMPLE_NAME
        assert inserted_user.email == SAMPLE_EMAIL
        assert inserted_user.password == HASHED_VALUE
        assert output.name == SAMPLE_NAME
        assert output.email == SAMPLE_EMAIL

    def test_raises_when_email_already_exists(self):
        repository = MagicMock()
        repository.find_by_email.return_value = User(
            name="Existing",
            email=SAMPLE_EMAIL,
            password=HASHED_VALUE,
        )

        use_case = CreateUserUseCase(repository, MagicMock())

        with pytest.raises(ConflictException):
            use_case.execute(_create_user_input())

        repository.insert.assert_not_called()
