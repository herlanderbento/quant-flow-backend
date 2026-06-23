from dataclasses import dataclass
from account.domain.exchange_credential_repository import (
    ExchangeCredentialFilter,
    ExchangeCredentialSearchInput,
    ExchangeCredentialSearchOutput,
    IExchangeCredentialRepository,
)
from account.domain.user import UserId
from account.domain.user_repository import IUserRepository
from shared.application.use_cases import UseCase
from shared.application.paginated_list_input import PaginatedListInput
from shared.application.paginated_list_output import PaginatedListOutput
from shared.domain.exceptions import NotFoundException
from account.application.use_cases.exchange_credential.common.exchange_credential_output import (
    ExchangeCredentialOutput,
)


@dataclass(slots=True, kw_only=True)
class GetExchangeCredentialsByUserInput(PaginatedListInput[ExchangeCredentialFilter]):
    user_id: UserId


@dataclass(slots=True)
class GetExchangeCredentialsByUserOutput(PaginatedListOutput[ExchangeCredentialOutput]):
    pass


class GetExchangeCredentialsByUserUseCase(UseCase):
    def __init__(
        self,
        exchange_credential_repository: IExchangeCredentialRepository,
        user_repository: IUserRepository,
    ):
        self.exchange_credential_repository = exchange_credential_repository
        self.user_repository = user_repository

    async def execute(
        self, input: GetExchangeCredentialsByUserInput
    ) -> GetExchangeCredentialsByUserOutput:

        if not await self.user_repository.find_by_id(input.user_id.value):
            raise NotFoundException(f"User with id {input.user_id} not found")

        search_input = ExchangeCredentialSearchInput(**input.to_search_input())

        search_output = await self.exchange_credential_repository.find_by_user_id(
            input.user_id.value, search_input
        )

        return self.__to_output(search_output)

    def __to_output(
        self, output: ExchangeCredentialSearchOutput
    ) -> GetExchangeCredentialsByUserOutput:
        items = list(map(ExchangeCredentialOutput.from_entity, output.items))
        return GetExchangeCredentialsByUserOutput.from_search_output(items, output)
