from uuid import UUID

from fastapi import APIRouter, Depends, Query, status

from account.domain.user import UserId
from shared.infra.api.auth_dependencies import AuthContext, require_authenticated
from trader.application.use_cases.trade.get_trades_by_user import (
    GetTradesByUserInput,
    GetTradesByUserUseCase,
)
from trader.domain.bot import BotId
from trader.domain.repositories.trade_repository import TradeFilter
from trader.infra.api.trade.trade_dependencies import get_get_trades_by_user_use_case
from trader.infra.api.trade.trade_presenter import TradeCollectionPresenter

router = APIRouter(prefix="/trades", tags=["Trades"])


@router.get("", response_model=TradeCollectionPresenter, status_code=status.HTTP_200_OK)
async def get_trades(
    page: int | None = Query(default=1, ge=1),
    per_page: int | None = Query(default=15, ge=1),
    sort: str | None = Query(default=None),
    sort_dir: str | None = Query(default=None),
    bot_id: UUID | None = Query(default=None),
    symbol: str | None = Query(default=None),
    trade_status: str | None = Query(default=None, alias="status"),
    side: str | None = Query(default=None),
    _auth: AuthContext = Depends(require_authenticated),
    use_case: GetTradesByUserUseCase = Depends(get_get_trades_by_user_use_case),
):
    output = await use_case.execute(
        GetTradesByUserInput(
            user_id=UserId(value=_auth.user_id),
            page=page,
            per_page=per_page,
            sort=sort,
            sort_dir=sort_dir,
            filter=TradeFilter(
                bot_id=BotId(value=bot_id) if bot_id else None,
                symbol=symbol,
                status=trade_status,
                side=side,
            ),
        )
    )
    return TradeCollectionPresenter.from_output(output)
