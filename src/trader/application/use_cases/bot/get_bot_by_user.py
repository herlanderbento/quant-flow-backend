from dataclasses import dataclass
from account.domain.user import UserId
from account.domain.user_repository import IUserRepository
from shared.application.paginated_list_input import PaginatedListInput
from shared.application.paginated_list_output import PaginatedListOutput
from shared.application.use_cases import UseCase
from shared.domain.exceptions import NotFoundException
from trader.application.use_cases.bot.common.bot_output import BotOutput
from trader.domain.repositories.bot_repository import (
    BotFilter,
    BotSearchInput,
    BotSearchOutput,
    IBotRepository,
)


@dataclass(slots=True, kw_only=True)
class GetBotByUserInput(PaginatedListInput[BotFilter]):
    user_id: UserId


@dataclass(slots=True)
class GetBotByUserOutput(PaginatedListOutput[BotOutput]):
    pass


class GetBotByUserUseCase(UseCase):
    def __init__(
        self, 
        bot_repository: IBotRepository, 
        user_repository: IUserRepository
    ):
        self.bot_repository = bot_repository
        self.user_repository = user_repository

    async def execute(self, input: GetBotByUserInput) -> GetBotByUserOutput:
        if not await self.user_repository.find_by_id(input.user_id.value):
            raise NotFoundException(f"User with id {input.user_id} not found")

        search_input = BotSearchInput(**input.to_search_input())

        search_output = await self.bot_repository.find_by_user_id(
            input.user_id, search_input
        )

        return self.__to_output(search_output)

    def __to_output(self, output: BotSearchOutput) -> GetBotByUserOutput:
        items = list(map(BotOutput.from_entity, output.items))
        return GetBotByUserOutput.from_search_output(items, output)
