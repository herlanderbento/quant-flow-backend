from dataclasses import dataclass
from uuid import UUID

from shared.application.cryptography import IPasswordHasher
from shared.application.use_cases import UseCase
from shared.domain.exceptions import (
    ConflictException,
    EntityValidationException,
    ForbiddenException,
    NotFoundException,
)
from account.application.use_cases.user.common.user_output import UserOutput
from account.domain.user import User
from account.domain.user_repository import IUserRepository


@dataclass
class UpdateUserInput:
    id: UUID
    requester_id: UUID
    name: str | None = None
    email: str | None = None
    password: str | None = None
    is_active: bool | None = None


@dataclass(frozen=True)
class UpdateUserOutput(UserOutput):
    pass


class UpdateUserUseCase(UseCase):
    def __init__(
        self,
        user_repo: IUserRepository,
        password_hasher: IPasswordHasher,
    ):
        self.user_repo = user_repo
        self.password_hasher = password_hasher

    async def execute(self, input: UpdateUserInput) -> UpdateUserOutput:
        if input.requester_id != input.id:
            raise ForbiddenException("You do not have permission to modify this User")

        user = await self.user_repo.find_by_id(input.id)

        if user is None:
            raise NotFoundException(f"User with id {input.id} not found")

        if input.name is not None:
            user.change_name(input.name)

        if input.email is not None and input.email != user.email:
            user_with_same_email = await self.user_repo.find_by_email(input.email)

            if user_with_same_email:
                raise ConflictException(f"User with email {input.email} already exists")

            user.change_email(input.email)

        if input.password is not None:
            hashed_password = self.password_hasher.hash(input.password)
            user.change_password(hashed_password)

        if input.is_active is True:
            user.activate()

        if input.is_active is False:
            user.deactivate()

        if user.notification.has_errors():
            raise EntityValidationException(user.notification.errors)

        await self.user_repo.update(user)

        return self.__to_output(user)

    def __to_output(self, user: User):
        return UpdateUserOutput.from_entity(user)