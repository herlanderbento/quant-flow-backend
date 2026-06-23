from dataclasses import dataclass
from account.domain.exchange_credential import ExchangeCredentialId
from account.domain.exchange_credential_repository import IExchangeCredentialRepository
from shared.application.use_cases import UseCase
from shared.domain.exceptions import NotFoundException


@dataclass
class DeleteExchangeCredentialInput:
    id: ExchangeCredentialId


class DeleteExchangeCredentialUseCase(UseCase):
    def __init__(
        self,
        exchange_credential_repository: IExchangeCredentialRepository,
    ):
        self.exchange_credential_repository = exchange_credential_repository

    async def execute(self, input: DeleteExchangeCredentialInput) -> None:
        if not await self.exchange_credential_repository.find_by_id(input.id.value):
            raise NotFoundException(f"Exchange credential with id {input.id} not found")

        await self.exchange_credential_repository.delete(input.id.value)
