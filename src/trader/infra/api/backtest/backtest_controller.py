from datetime import datetime
from uuid import UUID

from fastapi import APIRouter, Depends, Query, status
from pydantic import BaseModel, Field

from account.domain.user import UserId
from shared.infra.api.auth_dependencies import AuthContext, require_authenticated
from trader.application.use_cases.backtest.common.backtest_output import BacktestOutput
from trader.application.use_cases.backtest.create_backtest import (
    CreateBacktestInput,
    CreateBacktestUseCase,
)
from trader.application.use_cases.backtest.get_backtests_by_user import (
    GetBacktestsByUserInput,
    GetBacktestsByUserUseCase,
)
from trader.domain.bot import BotId
from trader.domain.repositories.backtest_repository import BacktestFilter
from trader.infra.api.backtest.backtest_dependencies import (
    get_create_backtest_use_case,
    get_get_backtests_by_user_use_case,
)
from trader.infra.api.backtest.backtest_presenter import BacktestCollectionPresenter

router = APIRouter(prefix="/backtests", tags=["Backtests"])


class CreateBacktestRequest(BaseModel):
    bot_id: UUID
    period_start: datetime
    period_end: datetime
    timeframe: str = Field(default="1h", pattern=r"^(15m|1h|4h|1d)$")


@router.post("", response_model=BacktestOutput, status_code=status.HTTP_201_CREATED)
async def create_backtest(
    request: CreateBacktestRequest,
    _auth: AuthContext = Depends(require_authenticated),
    use_case: CreateBacktestUseCase = Depends(get_create_backtest_use_case),
):
    return await use_case.execute(
        CreateBacktestInput(
            user_id=UserId(value=_auth.user_id),
            bot_id=BotId(value=request.bot_id),
            period_start=request.period_start,
            period_end=request.period_end,
            timeframe=request.timeframe,
        )
    )


@router.get(
    "", response_model=BacktestCollectionPresenter, status_code=status.HTTP_200_OK
)
async def get_backtests(
    page: int | None = Query(default=1, ge=1),
    per_page: int | None = Query(default=15, ge=1),
    sort: str | None = Query(default=None),
    sort_dir: str | None = Query(default=None),
    bot_id: UUID | None = Query(default=None),
    symbol: str | None = Query(default=None),
    strategy_type: str | None = Query(default=None),
    _auth: AuthContext = Depends(require_authenticated),
    use_case: GetBacktestsByUserUseCase = Depends(get_get_backtests_by_user_use_case),
):
    output = await use_case.execute(
        GetBacktestsByUserInput(
            user_id=UserId(value=_auth.user_id),
            page=page,
            per_page=per_page,
            sort=sort,
            sort_dir=sort_dir,
            filter=BacktestFilter(
                bot_id=BotId(value=bot_id) if bot_id else None,
                symbol=symbol,
                strategy_type=strategy_type,
            ),
        )
    )
    return BacktestCollectionPresenter.from_output(output)
