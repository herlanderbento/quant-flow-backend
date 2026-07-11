from fastapi import Depends
from sqlalchemy.ext.asyncio import AsyncSession

from account.infra.api.credential.credential_dependencies import (
    get_credential_repository,
)
from account.infra.api.user.user_dependencies import get_user_repository
from shared.infra.db.database import get_db_session
from account.domain.user_repository import IUserRepository
from account.domain.credential_repository import ICredentialRepository

from trader.application.use_cases.bot.change_bot_status import ChangeBotStatusUseCase
from trader.application.use_cases.bot.get_bot_by_user import GetBotByUserUseCase
from trader.domain.repositories.bot_repository import IBotRepository
from trader.infra.db.bot_postgres_repository import BotPostgresRepository
from trader.application.use_cases.bot.create_bot import CreateBotUseCase


def get_bot_repository(
    session: AsyncSession = Depends(get_db_session),
) -> IBotRepository:
    return BotPostgresRepository(session)


def get_create_bot_use_case(
    bot_repo: IBotRepository = Depends(get_bot_repository),
    user_repo: IUserRepository = Depends(get_user_repository),
    credential_repo: ICredentialRepository = Depends(get_credential_repository),
) -> CreateBotUseCase:
    return CreateBotUseCase(bot_repo, user_repo, credential_repo)


def get_get_bot_by_user_use_case(
    bot_repo: IBotRepository = Depends(get_bot_repository),
    user_repo: IUserRepository = Depends(get_user_repository),
) -> GetBotByUserUseCase:
    return GetBotByUserUseCase(bot_repo, user_repo)


def get_change_bot_status_use_case(
    bot_repo: IBotRepository = Depends(get_bot_repository),
    user_repo: IUserRepository = Depends(get_user_repository),
) -> ChangeBotStatusUseCase:
    return ChangeBotStatusUseCase(bot_repo, user_repo)
