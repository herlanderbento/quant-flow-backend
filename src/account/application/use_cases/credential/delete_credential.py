from dataclasses import dataclass
from account.domain.credential import CredentialId
from account.domain.credential_repository import ICredentialRepository
from account.domain.user import UserId
from shared.application.use_cases import UseCase
from shared.domain.exceptions import ForbiddenException, NotFoundException


@dataclass
class DeleteCredentialInput:
    id: CredentialId
    user_id: UserId


class DeleteCredentialUseCase(UseCase):
    def __init__(
        self,
        credential_repository: ICredentialRepository,
    ):
        self.credential_repository = credential_repository

    async def execute(self, input: DeleteCredentialInput) -> None:
        credential = await self.credential_repository.find_by_id(input.id.value)
        if not credential:
            raise NotFoundException(f"Exchange credential with id {input.id} not found")

        if credential.user_id.value != input.user_id.value:
            raise ForbiddenException("You do not have permission to delete this credential")

        await self.credential_repository.delete(input.id.value)
