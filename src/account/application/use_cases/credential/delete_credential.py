from dataclasses import dataclass
from account.domain.credential import CredentialId
from account.domain.credential_repository import ICredentialRepository
from shared.application.use_cases import UseCase
from shared.domain.exceptions import NotFoundException


@dataclass
class DeleteCredentialInput:
    id: CredentialId


class DeleteCredentialUseCase(UseCase):
    def __init__(
        self,
        credential_repository: ICredentialRepository,
    ):
        self.credential_repository = credential_repository

    async def execute(self, input: DeleteCredentialInput) -> None:
        if not await self.credential_repository.find_by_id(input.id.value):
            raise NotFoundException(f"Exchange credential with id {input.id} not found")

        await self.credential_repository.delete(input.id.value)
