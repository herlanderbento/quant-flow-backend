from dataclasses import dataclass

from account.domain.user import UserId
from account.domain.user_repository import IUserRepository
from shared.application.use_cases import UseCase
from shared.domain.exceptions import ForbiddenException, NotFoundException
from trader.application.use_cases.bot.common.bot_output import BotOutput
from trader.domain.bot import Bot, BotId
from trader.domain.repositories.bot_repository import IBotRepository


@dataclass
class ChangeBotStatusInput:
    bot_id: BotId
    user_id: UserId
    is_active: bool


@dataclass(frozen=True)
class ChangeBotStatusOutput(BotOutput):
    pass


class ChangeBotStatusUseCase(UseCase):
    def __init__(
        self, 
        bot_repository: IBotRepository, 
        user_repository: IUserRepository
    ):
        self.bot_repository = bot_repository
        self.user_repository = user_repository

    async def execute(self, input: ChangeBotStatusInput) -> ChangeBotStatusOutput:
        if not await self.user_repository.find_by_id(input.user_id.value):
            raise NotFoundException(f"User with id {input.user_id} not found")

        bot = await self.bot_repository.find_by_id(input.bot_id)
        if not bot:
            raise NotFoundException(f"Bot with id {input.bot_id} not found")

        if bot.user_id.value != input.user_id.value:
            raise ForbiddenException("You do not have permission to modify this Bot")

        if input.is_active:
            bot.activate()
        else:
            bot.deactivate()

        await self.bot_repository.update(bot)

        return self.__to_output(bot)

    def __to_output(self, bot: Bot) -> ChangeBotStatusOutput:
        return ChangeBotStatusOutput.from_entity(bot)
