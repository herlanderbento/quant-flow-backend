from fastapi import Depends
from sqlalchemy.ext.asyncio import AsyncSession

from account.domain.user_repository import IUserRepository
from account.infra.api.user.user_dependencies import get_user_repository
from shared.infra.db.config import settings
from shared.infra.db.database import get_db_session
from trader.application.backtest_engine import BacktestCosts
from trader.application.use_cases.backtest.create_backtest import CreateBacktestUseCase
from trader.application.use_cases.backtest.get_backtests_by_user import (
    GetBacktestsByUserUseCase,
)
from trader.domain.repositories.backtest_repository import IBacktestRepository
from trader.domain.repositories.bot_repository import IBotRepository
from trader.infra.api.bot.bot_dependencies import get_bot_repository
from trader.infra.db.backtest_postgres_repository import BacktestPostgresRepository


def get_backtest_repository(
    session: AsyncSession = Depends(get_db_session),
) -> IBacktestRepository:
    return BacktestPostgresRepository(session)


def get_create_backtest_use_case(
    bot_repo: IBotRepository = Depends(get_bot_repository),
    backtest_repo: IBacktestRepository = Depends(get_backtest_repository),
    user_repo: IUserRepository = Depends(get_user_repository),
) -> CreateBacktestUseCase:
    costs = BacktestCosts(
        taker_fee_rate=settings.PAPER_TAKER_FEE_RATE,
        slippage_bps=settings.PAPER_SLIPPAGE_BPS,
    )
    return CreateBacktestUseCase(bot_repo, backtest_repo, user_repo, costs)


def get_get_backtests_by_user_use_case(
    backtest_repo: IBacktestRepository = Depends(get_backtest_repository),
    user_repo: IUserRepository = Depends(get_user_repository),
) -> GetBacktestsByUserUseCase:
    return GetBacktestsByUserUseCase(backtest_repo, user_repo)
