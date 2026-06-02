from dataclasses import dataclass
from uuid import UUID

from shared.application.use_cases import UseCase
from shared.domain.exceptions import NotFoundException
from account.domain.user_repository import IUserRepository


@dataclass
class DeleteUserInput:
    user_id: UUID


class DeleteUserUseCase(UseCase):
    def __init__(self, user_repository: IUserRepository):
        self.user_repository = user_repository

    async def execute(self, input: DeleteUserInput) -> None:
        user = await self.user_repository.find_by_id(input.user_id)
        if user is None:
            raise NotFoundException(f"User with id {input.user_id} not found")
        await self.user_repository.delete(user.id.value)
