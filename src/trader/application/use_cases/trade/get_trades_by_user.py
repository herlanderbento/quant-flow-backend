from dataclasses import dataclass

from account.domain.user import UserId
from account.domain.user_repository import IUserRepository
from shared.application.paginated_list_input import PaginatedListInput
from shared.application.paginated_list_output import PaginatedListOutput
from shared.application.use_cases import UseCase
from shared.domain.exceptions import NotFoundException
from trader.application.use_cases.trade.common.trade_output import TradeOutput
from trader.domain.repositories.trade_repository import (
    ITradeRepository,
    TradeFilter,
    TradeSearchInput,
    TradeSearchOutput,
)


@dataclass(slots=True, kw_only=True)
class GetTradesByUserInput(PaginatedListInput[TradeFilter]):
    user_id: UserId


@dataclass(slots=True)
class GetTradesByUserOutput(PaginatedListOutput[TradeOutput]):
    pass


class GetTradesByUserUseCase(UseCase):
    def __init__(
        self,
        trade_repository: ITradeRepository,
        user_repository: IUserRepository,
    ):
        self.trade_repository = trade_repository
        self.user_repository = user_repository

    async def execute(self, input: GetTradesByUserInput) -> GetTradesByUserOutput:
        if not await self.user_repository.find_by_id(input.user_id.value):
            raise NotFoundException(f"User with id {input.user_id} not found")

        search_input = TradeSearchInput(**input.to_search_input())
        search_output = await self.trade_repository.find_by_user_id(
            input.user_id, search_input
        )
        return self.__to_output(search_output)

    def __to_output(self, output: TradeSearchOutput) -> GetTradesByUserOutput:
        items = list(map(TradeOutput.from_entity, output.items))
        return GetTradesByUserOutput.from_search_output(items, output)
