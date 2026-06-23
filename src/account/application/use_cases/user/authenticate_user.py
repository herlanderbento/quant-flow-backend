from dataclasses import dataclass

from account.application.use_cases.user.common.user_output import UserOutput
from account.domain.user import User
from shared.application.use_cases import UseCase
from account.domain.user_repository import IUserRepository
from shared.application.cryptography import IPasswordHasher
from shared.application.token_generator import ITokenGenerator
from shared.domain.exceptions import UnauthorizedException


@dataclass
class AuthenticateUserInput:
    email: str
    password: str


@dataclass(frozen=True)
class AuthenticateUserOutput:
    access_token: str
    refresh_token: str
    user: UserOutput


class AuthenticateUserUseCase(UseCase):
    def __init__(
        self,
        user_repository: IUserRepository,
        token_generator: ITokenGenerator,
        password_hasher: IPasswordHasher,
    ):
        self.user_repository = user_repository
        self.token_generator = token_generator
        self.password_hasher = password_hasher

    async def execute(self, input: AuthenticateUserInput) -> AuthenticateUserOutput:
        user = await self.user_repository.find_by_email(input.email)

        if user is None:
            raise UnauthorizedException("Password or email is incorrect")

        if not self.password_hasher.verify(input.password, user.password):
            raise UnauthorizedException("Password or email is incorrect")

        return self.__to_output(user)

    def __to_output(self, user: User) -> AuthenticateUserOutput:
        subject = str(user.id.value)
        return AuthenticateUserOutput(
            access_token=self.token_generator.generate(
                {"sub": subject, "type": "access"}
            ),
            refresh_token=self.token_generator.generate(
                {"sub": subject, "type": "refresh"}
            ),
            user=UserOutput.from_entity(user),
        )
