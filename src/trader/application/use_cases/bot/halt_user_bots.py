from dataclasses import dataclass

from account.domain.user import UserId
from shared.application.use_cases import UseCase
from trader.domain.repositories.bot_repository import IBotRepository


@dataclass
class HaltUserBotsInput:
    user_id: UserId


@dataclass(frozen=True)
class HaltUserBotsOutput:
    deactivated_bot_ids: list[str]


class HaltUserBotsUseCase(UseCase):
    """
    Emergency stop for one user: no bot of theirs opens new positions.
    Open positions keep being protected and closed by the worker.
    """

    def __init__(self, bot_repository: IBotRepository):
        self.bot_repository = bot_repository

    async def execute(self, input: HaltUserBotsInput) -> HaltUserBotsOutput:
        bots = await self.bot_repository.find_active_by_user(input.user_id)
        for bot in bots:
            bot.deactivate()
            await self.bot_repository.update(bot)
        return HaltUserBotsOutput(deactivated_bot_ids=[str(bot.id.value) for bot in bots])
