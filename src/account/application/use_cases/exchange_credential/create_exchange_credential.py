from dataclasses import dataclass
from account.application.use_cases.exchange_credential.common.exchange_credential_output import (
    ExchangeCredentialOutput,
)
from account.domain.user import UserId
from account.domain.exchange_credential import (
    ExchangeCredential,
    ExchangeCredentialCreateCommand,
)
from account.domain.exchange_credential_repository import IExchangeCredentialRepository
from account.domain.user_repository import IUserRepository
from shared.application.cryptography import IEncryption
from shared.application.use_cases import UseCase
from shared.domain.exceptions import NotFoundException


@dataclass
class CreateExchangeCredentialInput:
    user_id: UserId
    exchange_name: str
    api_key: str
    api_secret: str
    is_testnet: bool


@dataclass(frozen=True)
class CreateExchangeCredentialOutput(ExchangeCredentialOutput):
    pass


class CreateExchangeCredentialUseCase(UseCase):
    def __init__(
        self,
        exchange_credential_repository: IExchangeCredentialRepository,
        encryption: IEncryption,
        user_repository: IUserRepository,
    ):
        self.exchange_credential_repository = exchange_credential_repository
        self.encryption = encryption
        self.user_repository = user_repository

    async def execute(
        self, input: CreateExchangeCredentialInput
    ) -> CreateExchangeCredentialOutput:

        if not await self.user_repository.find_by_id(input.user_id.value):
            raise NotFoundException(f"User with id {input.user_id} not found")

        active_credentials = (
            await self.exchange_credential_repository.find_active_by_user_exchange(
                input.user_id.value,
                input.exchange_name,
                input.is_testnet,
            )
        )

        for credential in active_credentials:
            credential.deactivate()
            await self.exchange_credential_repository.update(credential)

        secret_encrypted = self.encryption.encrypt(input.api_secret)

        command = ExchangeCredentialCreateCommand(
            user_id=input.user_id,
            exchange_name=input.exchange_name,
            api_key=input.api_key,
            api_secret_encrypted=secret_encrypted,
            is_testnet=input.is_testnet,
        )

        exchange_credential = ExchangeCredential.create(command)

        await self.exchange_credential_repository.insert(exchange_credential)

        return self.__to_output(exchange_credential)

    def __to_output(
        self, exchange_credential: ExchangeCredential
    ) -> CreateExchangeCredentialOutput:
        return CreateExchangeCredentialOutput.from_entity(exchange_credential)
