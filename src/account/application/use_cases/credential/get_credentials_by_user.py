from dataclasses import dataclass
from account.domain.credential_repository import (
    CredentialFilter,
    CredentialSearchInput,
    CredentialSearchOutput,
    ICredentialRepository,
)
from account.domain.user import UserId
from account.domain.user_repository import IUserRepository
from shared.application.use_cases import UseCase
from shared.application.paginated_list_input import PaginatedListInput
from shared.application.paginated_list_output import PaginatedListOutput
from shared.domain.exceptions import NotFoundException
from account.application.use_cases.credential.common.credential_output import (
    CredentialOutput,
)


@dataclass(slots=True, kw_only=True)
class GetCredentialsByUserInput(PaginatedListInput[CredentialFilter]):
    user_id: UserId


@dataclass(slots=True)
class GetCredentialsByUserOutput(PaginatedListOutput[CredentialOutput]):
    pass


class GetCredentialsByUserUseCase(UseCase):
    def __init__(
        self,
        credential_repository: ICredentialRepository,
        user_repository: IUserRepository,
    ):
        self.credential_repository = credential_repository
        self.user_repository = user_repository

    async def execute(
        self, input: GetCredentialsByUserInput
    ) -> GetCredentialsByUserOutput:

        if not await self.user_repository.find_by_id(input.user_id.value):
            raise NotFoundException(f"User with id {input.user_id} not found")

        search_input = CredentialSearchInput(**input.to_search_input())

        search_output = await self.credential_repository.find_by_user_id(
            input.user_id.value, search_input
        )

        return self.__to_output(search_output)

    def __to_output(self, output: CredentialSearchOutput) -> GetCredentialsByUserOutput:
        items = list(map(CredentialOutput.from_entity, output.items))
        return GetCredentialsByUserOutput.from_search_output(items, output)
