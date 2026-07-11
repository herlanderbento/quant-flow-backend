from dataclasses import dataclass

from account.application.use_cases.credential.common.credential_output import (
    CredentialOutput,
)
from account.domain.credential_repository import (
    ICredentialRepository,
    CredentialFilter,
    CredentialSearchInput,
    CredentialSearchOutput,
)
from shared.application.paginated_list_input import PaginatedListInput
from shared.application.paginated_list_output import PaginatedListOutput
from shared.application.use_cases import UseCase


@dataclass(slots=True)
class ListCredentialsInput(PaginatedListInput[CredentialFilter]):
    pass


@dataclass(slots=True)
class ListCredentialsOutput(PaginatedListOutput[CredentialOutput]):
    pass


class ListCredentialsUseCase(UseCase):
    def __init__(self, credential_repository: ICredentialRepository):
        self.credential_repository = credential_repository

    def execute(self, input: ListCredentialsInput) -> ListCredentialsOutput:
        search_input = CredentialSearchInput(**input.to_input())

        search_output = self.credential_repository.search(search_input)

        return self.__to_output(search_output)

    def __to_output(self, output: CredentialSearchOutput) -> ListCredentialsOutput:
        items = list(map(CredentialOutput.from_entity, output.items))
        return ListCredentialsOutput.from_search_output(items, output)
