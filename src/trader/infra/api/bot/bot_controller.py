from typing import Annotated
from uuid import UUID

from fastapi import APIRouter, Depends, Query, status
from pydantic import BaseModel, StringConstraints, Field

from account.domain.credential import CredentialId
from account.domain.user import UserId
from shared.infra.api.auth_dependencies import AuthContext, require_authenticated

from trader.application.use_cases.bot.change_bot_status import (
    ChangeBotStatusInput,
    ChangeBotStatusOutput,
    ChangeBotStatusUseCase,
)
from trader.application.use_cases.bot.create_bot import CreateBotInput, CreateBotUseCase
from trader.application.use_cases.bot.common.bot_output import BotOutput
from trader.application.use_cases.bot.get_bot_by_user import (
    GetBotByUserInput,
    GetBotByUserUseCase,
)
from trader.domain.bot import BotId
from trader.domain.repositories.bot_repository import BotFilter
from trader.infra.api.bot.bot_dependencies import (
    get_change_bot_status_use_case,
    get_create_bot_use_case,
    get_get_bot_by_user_use_case,
)
from trader.infra.api.bot.bot_presenter import BotCollectionPresenter

router = APIRouter(prefix="/bots", tags=["Trader Bots"])

NonEmptyStr = Annotated[str, StringConstraints(strip_whitespace=True, min_length=1)]


class CreateBotRequest(BaseModel):
    credential_id: UUID
    name: NonEmptyStr
    symbol: NonEmptyStr = Field(
        pattern=r"^[A-Z0-9]{2,10}/[A-Z0-9]{2,10}$",
        examples=["BTC/USDT"],
        description="Trading pair in BASE/QUOTE format (uppercase)",
    )
    strategy_type: NonEmptyStr
    is_active: bool = False
    allocated_capital: float = Field(
        gt=0, description="Capital must be greater than zero"
    )
    stop_loss_pct: float = Field(ge=0, le=100)
    take_profit_pct: float = Field(ge=0)


@router.post("", response_model=BotOutput, status_code=status.HTTP_201_CREATED)
async def create_bot(
    request: CreateBotRequest,
    _auth: AuthContext = Depends(require_authenticated),
    use_case: CreateBotUseCase = Depends(get_create_bot_use_case),
):
    output = await use_case.execute(
        CreateBotInput(
            user_id=UserId(value=_auth.user_id),
            credential_id=CredentialId(value=request.credential_id),
            name=request.name,
            symbol=request.symbol,
            strategy_type=request.strategy_type,
            is_active=request.is_active,
            allocated_capital=request.allocated_capital,
            stop_loss_pct=request.stop_loss_pct,
            take_profit_pct=request.take_profit_pct,
        )
    )
    return output


@router.get("", response_model=BotCollectionPresenter, status_code=status.HTTP_200_OK)
async def get_bots(
    page: int | None = Query(default=1, ge=1),
    per_page: int | None = Query(default=15, ge=1),
    sort: str | None = Query(default=None),
    sort_dir: str | None = Query(default=None),
    name: str | None = Query(default=None),
    strategy_type: str | None = Query(default=None),
    is_active: bool | None = Query(default=None),
    _auth: AuthContext = Depends(require_authenticated),
    use_case: GetBotByUserUseCase = Depends(get_get_bot_by_user_use_case),
):
    output = await use_case.execute(
        GetBotByUserInput(
            user_id=UserId(value=_auth.user_id),
            page=page,
            per_page=per_page,
            sort=sort,
            sort_dir=sort_dir,
            filter=BotFilter(
                name=name, strategy_type=strategy_type, is_active=is_active
            ),
        )
    )
    return BotCollectionPresenter.from_output(output)


@router.patch(
    "/{bot_id}/activate",
    response_model=ChangeBotStatusOutput,
    status_code=status.HTTP_200_OK,
)
async def activate_bot(
    bot_id: UUID,
    _auth: AuthContext = Depends(require_authenticated),
    use_case: ChangeBotStatusUseCase = Depends(get_change_bot_status_use_case),
):
    output = await use_case.execute(
        ChangeBotStatusInput(
            bot_id=BotId(value=bot_id),
            user_id=UserId(value=_auth.user_id),
            is_active=True,
        )
    )
    return output


@router.patch(
    "/{bot_id}/deactivate",
    response_model=ChangeBotStatusOutput,
    status_code=status.HTTP_200_OK,
)
async def deactivate_bot(
    bot_id: UUID,
    _auth: AuthContext = Depends(require_authenticated),
    use_case: ChangeBotStatusUseCase = Depends(get_change_bot_status_use_case),
):
    output = await use_case.execute(
        ChangeBotStatusInput(
            bot_id=BotId(value=bot_id),
            user_id=UserId(value=_auth.user_id),
            is_active=False,
        )
    )
    return output
