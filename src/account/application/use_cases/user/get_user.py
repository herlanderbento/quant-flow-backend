from dataclasses import dataclass

from account.application.use_cases.user.common.user_output import UserOutput
from account.domain.user import User, UserId
from account.domain.user_repository import IUserRepository
from shared.application.use_cases import UseCase
from shared.domain.exceptions import ForbiddenException, NotFoundException


@dataclass
class GetUserInput:
    user_id: UserId
    requester_id: UserId


@dataclass(frozen=True)
class GetUserOutput(UserOutput):
    pass


class GetUserUseCase(UseCase):
    def __init__(
        self,
        user_repository: IUserRepository,
    ):
        self.user_repository = user_repository

    async def execute(self, input: GetUserInput) -> GetUserOutput:
        if input.requester_id.value != input.user_id.value:
            raise ForbiddenException("You do not have permission to access this User")

        user = await self.user_repository.find_by_id(input.user_id.value)
        if user is not None:
            return self.__to_output(user)
        raise NotFoundException(f"User with id {input.user_id} not found")

    def __to_output(self, entity: User) -> GetUserOutput:
        return GetUserOutput.from_entity(entity)
