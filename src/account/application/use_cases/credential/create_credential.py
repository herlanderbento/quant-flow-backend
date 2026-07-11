from dataclasses import dataclass
from account.application.use_cases.credential.common.credential_output import (
    CredentialOutput,
)
from account.domain.user import UserId
from account.domain.credential import (
    Credential,
    CredentialCreateCommand,
)
from account.domain.credential_repository import ICredentialRepository
from account.domain.user_repository import IUserRepository
from shared.application.cryptography import IEncryption
from shared.application.use_cases import UseCase
from shared.domain.exceptions import NotFoundException


@dataclass
class CreateCredentialInput:
    user_id: UserId
    name: str
    api_key: str
    api_secret: str
    is_testnet: bool


@dataclass(frozen=True)
class CreateCredentialOutput(CredentialOutput):
    pass


class CreateCredentialUseCase(UseCase):
    def __init__(
        self,
        credential_repository: ICredentialRepository,
        encryption: IEncryption,
        user_repository: IUserRepository,
    ):
        self.credential_repository = credential_repository
        self.encryption = encryption
        self.user_repository = user_repository

    async def execute(self, input: CreateCredentialInput) -> CreateCredentialOutput:

        if not await self.user_repository.find_by_id(input.user_id.value):
            raise NotFoundException(f"User with id {input.user_id} not found")

        active_credentials = await self.credential_repository.find_active_by_user(
            input.user_id.value,
            input.name,
            input.is_testnet,
        )

        for credential in active_credentials:
            credential.deactivate()
            await self.credential_repository.update(credential)

        secret_encrypted = self.encryption.encrypt(input.api_secret)

        command = CredentialCreateCommand(
            user_id=input.user_id,
            name=input.name,
            api_key=input.api_key,
            api_secret=secret_encrypted,
            is_testnet=input.is_testnet,
        )

        credential = Credential.create(command)

        await self.credential_repository.insert(credential)

        return self.__to_output(credential)

    def __to_output(self, credential: Credential) -> CreateCredentialOutput:
        return CreateCredentialOutput.from_entity(credential)
