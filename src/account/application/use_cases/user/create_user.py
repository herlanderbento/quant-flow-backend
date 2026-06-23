from account.application.use_cases.user.common.user_output import UserOutput
from account.domain.user import User, UserCreateCommand
from account.domain.user_repository import IUserRepository
from shared.application.cryptography import IPasswordHasher
from shared.application.use_cases import UseCase

from dataclasses import dataclass

from shared.domain.exceptions import ConflictException


@dataclass
class CreateUserInput:
    name: str
    email: str
    password: str


@dataclass(frozen=True)
class CreateUserOutput(UserOutput):
    pass


class CreateUserUseCase(UseCase):
    def __init__(
        self,
        user_repository: IUserRepository,
        password_hasher: IPasswordHasher,
    ):
        self.user_repository = user_repository
        self.password_hasher = password_hasher

    async def execute(self, input: CreateUserInput) -> CreateUserOutput:

        if await self.user_repository.find_by_email(input.email):
            raise ConflictException(f"User with email {input.email} already exists")

        hashed_password = self.password_hasher.hash(input.password)

        command = UserCreateCommand(
            name=input.name,
            email=input.email,
            password=hashed_password,
        )
        user = User.create(command)

        await self.user_repository.insert(user)

        return self.__to_output(user)

    def __to_output(self, user: User):
        return CreateUserOutput.from_entity(user)
