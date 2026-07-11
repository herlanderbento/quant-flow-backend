from dataclasses import dataclass

from account.domain.credential import CredentialId
from account.domain.credential_repository import ICredentialRepository
from account.domain.user import UserId
from account.domain.user_repository import IUserRepository

from shared.application.use_cases import UseCase
from shared.domain.exceptions import NotFoundException, ConflictException

from trader.application.use_cases.bot.common.bot_output import BotOutput
from trader.domain.bot import Bot, BotCreateCommand
from trader.domain.repositories.bot_repository import IBotRepository


@dataclass
class CreateBotInput:
    user_id: UserId
    credential_id: CredentialId
    name: str
    symbol: str
    strategy_type: str
    is_active: bool
    allocated_capital: float
    stop_loss_pct: float
    take_profit_pct: float


@dataclass(frozen=True)
class CreateBotOutput(BotOutput):
    pass


class CreateBotUseCase(UseCase):
    def __init__(
        self,
        bot_repository: IBotRepository,
        user_repository: IUserRepository,
        credential_repository: ICredentialRepository,
    ):
        self.bot_repository = bot_repository
        self.user_repository = user_repository
        self.credential_repository = credential_repository

    async def execute(self, input: CreateBotInput) -> CreateBotOutput:
        if not await self.user_repository.find_by_id(input.user_id.value):
            raise NotFoundException(f"User with id {input.user_id.value} not found")

        credential = await self.credential_repository.find_by_id(
            input.credential_id.value
        )
        if not credential:
            raise NotFoundException(
                f"Credential with id {input.credential_id.value} not found"
            )

        if credential.user_id.value != input.user_id.value:
            raise ConflictException(
                "The provided credential does not belong to this user"
            )

        command = BotCreateCommand(
            user_id=input.user_id,
            credential_id=input.credential_id,
            name=input.name,
            symbol=input.symbol,
            strategy_type=input.strategy_type,
            is_active=input.is_active,
            allocated_capital=input.allocated_capital,
            stop_loss_pct=input.stop_loss_pct,
            take_profit_pct=input.take_profit_pct,
        )

        bot = Bot.create(command)

        await self.bot_repository.insert(bot)

        return self.__to_output(bot)

    def __to_output(self, bot: Bot) -> CreateBotOutput:
        return CreateBotOutput.from_entity(bot)
