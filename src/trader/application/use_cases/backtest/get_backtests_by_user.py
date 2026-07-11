from dataclasses import dataclass

from account.domain.user import UserId
from account.domain.user_repository import IUserRepository
from shared.application.paginated_list_input import PaginatedListInput
from shared.application.paginated_list_output import PaginatedListOutput
from shared.application.use_cases import UseCase
from shared.domain.exceptions import NotFoundException
from trader.application.use_cases.backtest.common.backtest_output import BacktestOutput
from trader.domain.repositories.backtest_repository import (
    BacktestFilter,
    BacktestSearchInput,
    BacktestSearchOutput,
    IBacktestRepository,
)


@dataclass(slots=True, kw_only=True)
class GetBacktestsByUserInput(PaginatedListInput[BacktestFilter]):
    user_id: UserId


@dataclass(slots=True)
class GetBacktestsByUserOutput(PaginatedListOutput[BacktestOutput]):
    pass


class GetBacktestsByUserUseCase(UseCase):
    def __init__(
        self,
        backtest_repository: IBacktestRepository,
        user_repository: IUserRepository,
    ):
        self.backtest_repository = backtest_repository
        self.user_repository = user_repository

    async def execute(self, input: GetBacktestsByUserInput) -> GetBacktestsByUserOutput:
        if not await self.user_repository.find_by_id(input.user_id.value):
            raise NotFoundException(f"User with id {input.user_id} not found")

        search_input = BacktestSearchInput(**input.to_search_input())
        search_output = await self.backtest_repository.find_by_user_id(
            input.user_id, search_input
        )
        return self.__to_output(search_output)

    def __to_output(self, output: BacktestSearchOutput) -> GetBacktestsByUserOutput:
        items = list(map(BacktestOutput.from_entity, output.items))
        return GetBacktestsByUserOutput.from_search_output(items, output)
