from dataclasses import dataclass
from account.domain.exchange_credential_repository import (
    ExchangeCredentialFilter,
    ExchangeCredentialSearchInput,
    ExchangeCredentialSearchOutput,
    IExchangeCredentialRepository,
)
from account.domain.user import UserId
from shared.application.use_cases import UseCase
from shared.application.paginated_list_input import PaginatedListInput
from shared.application.paginated_list_output import PaginatedListOutput
from account.application.use_cases.exchange_credential.common.exchange_credential_output import (
    ExchangeCredentialOutput,
)


@dataclass(slots=True)
class GetExchangeCredentialsByUserInput(PaginatedListInput[ExchangeCredentialFilter]):
    user_id: UserId


@dataclass(slots=True)
class GetExchangeCredentialsByUserOutput(PaginatedListOutput[ExchangeCredentialOutput]):
    pass


class GetExchangeCredentialsByUserUseCase(UseCase):
    def __init__(self, exchange_credential_repository: IExchangeCredentialRepository):
        self.exchange_credential_repository = exchange_credential_repository

    def execute(
        self, input: GetExchangeCredentialsByUserInput
    ) -> GetExchangeCredentialsByUserOutput:

        search_input = ExchangeCredentialSearchInput(**input.to_input())

        search_output = self.exchange_credential_repository.find_by_user_id(
            input.user_id, search_input
        )

        return self.__to_output(search_output)

    def __to_output(
        self, output: ExchangeCredentialSearchOutput
    ) -> GetExchangeCredentialsByUserOutput:
        items = list(map(ExchangeCredentialOutput.from_entity, output.items))
        return GetExchangeCredentialsByUserOutput.from_search_output(items, output)
