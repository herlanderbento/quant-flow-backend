from fastapi import Depends
from sqlalchemy.ext.asyncio import AsyncSession

from account.infra.api.user.user_dependencies import get_user_repository
from account.domain.user_repository import IUserRepository
from shared.infra.db.database import get_db_session
from trader.application.use_cases.trade.get_trades_by_user import GetTradesByUserUseCase
from trader.domain.repositories.trade_repository import ITradeRepository
from trader.infra.db.trade_postgres_repository import TradePostgresRepository


def get_trade_repository(
    session: AsyncSession = Depends(get_db_session),
) -> ITradeRepository:
    return TradePostgresRepository(session)


def get_get_trades_by_user_use_case(
    trade_repo: ITradeRepository = Depends(get_trade_repository),
    user_repo: IUserRepository = Depends(get_user_repository),
) -> GetTradesByUserUseCase:
    return GetTradesByUserUseCase(trade_repo, user_repo)
