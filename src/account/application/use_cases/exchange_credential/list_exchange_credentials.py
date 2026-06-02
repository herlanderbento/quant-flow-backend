from dataclasses import dataclass

from account.application.use_cases.exchange_credential.common.exchange_credential_output import (
    ExchangeCredentialOutput,
)
from account.domain.exchange_credential_repository import (
    IExchangeCredentialRepository,
    ExchangeCredentialFilter,
    ExchangeCredentialSearchInput,
    ExchangeCredentialSearchOutput,
)
from shared.application.paginated_list_input import PaginatedListInput
from shared.application.paginated_list_output import PaginatedListOutput
from shared.application.use_cases import UseCase


@dataclass(slots=True)
class ListExchangeCredentialsInput(PaginatedListInput[ExchangeCredentialFilter]):
    pass


@dataclass(slots=True)
class ListExchangeCredentialsOutput(PaginatedListOutput[ExchangeCredentialOutput]):
    pass


class ListExchangeCredentialsUseCase(UseCase):
    def __init__(self, exchange_credential_repository: IExchangeCredentialRepository):
        self.exchange_credential_repository = exchange_credential_repository

    def execute(self, input: ListExchangeCredentialsInput) -> ListExchangeCredentialsOutput:
        search_input = ExchangeCredentialSearchInput(**input.to_input())

        search_output = self.exchange_credential_repository.search(search_input)

        return self.__to_output(search_output)

    def __to_output(self, output: ExchangeCredentialSearchOutput) -> ListExchangeCredentialsOutput:
        items = list(map(ExchangeCredentialOutput.from_entity, output.items))
        return ListExchangeCredentialsOutput.from_search_output(items, output)
