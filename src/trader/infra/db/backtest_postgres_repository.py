from typing import List, Optional, Set, Type

from sqlalchemy import asc, delete, desc, func, select, update
from sqlalchemy.ext.asyncio import AsyncSession

from account.domain.user import UserId
from trader.domain.backtest_result import BacktestResult, BacktestResultId
from trader.domain.bot import BotId
from trader.domain.repositories.backtest_repository import (
    BacktestSearchInput,
    BacktestSearchOutput,
    IBacktestRepository,
)
from trader.infra.db.sql_models import BacktestResultModel, BotConfigModel


def _to_model(entity: BacktestResult) -> BacktestResultModel:
    return BacktestResultModel(
        id=entity.id.value,
        bot_config_id=entity.bot_id.value,
        strategy_type=entity.strategy_type,
        symbol=entity.symbol,
        period_start=entity.period_start,
        period_end=entity.period_end,
        total_return_pct=entity.total_return_pct,
        sharpe_ratio=entity.sharpe_ratio,
        max_drawdown_pct=entity.max_drawdown_pct,
        win_rate=entity.win_rate,
        total_trades=entity.total_trades,
        timeframe=entity.timeframe,
        profit_factor=entity.profit_factor,
        expectancy_pct=entity.expectancy_pct,
        buy_and_hold_return_pct=entity.buy_and_hold_return_pct,
        exposure_pct=entity.exposure_pct,
        fees_paid=entity.fees_paid,
        taker_fee_rate=entity.taker_fee_rate,
        slippage_bps=entity.slippage_bps,
        created_at=entity.created_at,
    )


def _float_or_none(value) -> float | None:
    return float(value) if value is not None else None


def _to_entity(model: BacktestResultModel) -> BacktestResult:
    return BacktestResult(
        id=BacktestResultId(value=model.id),
        bot_id=BotId(str(model.bot_config_id)),
        strategy_type=model.strategy_type,
        symbol=model.symbol,
        period_start=model.period_start,
        period_end=model.period_end,
        total_return_pct=(
            float(model.total_return_pct) if model.total_return_pct is not None else None
        ),
        sharpe_ratio=float(model.sharpe_ratio) if model.sharpe_ratio is not None else None,
        max_drawdown_pct=(
            float(model.max_drawdown_pct) if model.max_drawdown_pct is not None else None
        ),
        win_rate=float(model.win_rate) if model.win_rate is not None else None,
        total_trades=model.total_trades,
        timeframe=model.timeframe,
        profit_factor=_float_or_none(model.profit_factor),
        expectancy_pct=_float_or_none(model.expectancy_pct),
        buy_and_hold_return_pct=_float_or_none(model.buy_and_hold_return_pct),
        exposure_pct=_float_or_none(model.exposure_pct),
        fees_paid=_float_or_none(model.fees_paid),
        taker_fee_rate=_float_or_none(model.taker_fee_rate),
        slippage_bps=_float_or_none(model.slippage_bps),
        created_at=model.created_at,
    )


class BacktestPostgresRepository(IBacktestRepository):
    sortable_fields: List[str] = ["created_at", "symbol", "strategy_type", "total_return_pct"]

    def __init__(self, session: AsyncSession):
        self.session = session

    async def insert(self, entity: BacktestResult) -> None:
        self.session.add(_to_model(entity))
        await self.session.flush()

    async def bulk_insert(self, entities: List[BacktestResult]) -> None:
        self.session.add_all([_to_model(entity) for entity in entities])
        await self.session.flush()

    async def find_by_id(self, entity_id: BacktestResultId) -> Optional[BacktestResult]:
        result = await self.session.execute(
            select(BacktestResultModel).where(BacktestResultModel.id == entity_id.value)
        )
        model = result.scalar_one_or_none()
        return _to_entity(model) if model else None

    async def find_all(self) -> List[BacktestResult]:
        result = await self.session.execute(select(BacktestResultModel))
        return [_to_entity(model) for model in result.scalars().all()]

    async def find_by_ids(
        self, entity_ids: Set[BacktestResultId]
    ) -> List[BacktestResult]:
        raw_ids = [entity_id.value for entity_id in entity_ids]
        result = await self.session.execute(
            select(BacktestResultModel).where(BacktestResultModel.id.in_(raw_ids))
        )
        return [_to_entity(model) for model in result.scalars().all()]

    async def update(self, entity: BacktestResult) -> None:
        await self.session.execute(
            update(BacktestResultModel)
            .where(BacktestResultModel.id == entity.id.value)
            .values(
                total_return_pct=entity.total_return_pct,
                sharpe_ratio=entity.sharpe_ratio,
                max_drawdown_pct=entity.max_drawdown_pct,
                win_rate=entity.win_rate,
                total_trades=entity.total_trades,
            )
        )

    async def delete(self, entity_id: BacktestResultId) -> None:
        await self.session.execute(
            delete(BacktestResultModel).where(BacktestResultModel.id == entity_id.value)
        )

    async def find_by_user_id(
        self, user_id: UserId, input_data: BacktestSearchInput
    ) -> BacktestSearchOutput:
        query = (
            select(BacktestResultModel)
            .join(BotConfigModel, BacktestResultModel.bot_config_id == BotConfigModel.id)
            .where(BotConfigModel.user_id == user_id.value)
        )
        return await self._execute_search(query, input_data)

    async def search(self, input_data: BacktestSearchInput) -> BacktestSearchOutput:
        query = select(BacktestResultModel)
        return await self._execute_search(query, input_data)

    async def _execute_search(
        self, base_query, input_data: BacktestSearchInput
    ) -> BacktestSearchOutput:
        query = base_query

        if input_data.filter:
            if input_data.filter.bot_id:
                query = query.where(
                    BacktestResultModel.bot_config_id == input_data.filter.bot_id.value
                )
            if input_data.filter.symbol:
                query = query.where(BacktestResultModel.symbol == input_data.filter.symbol)
            if input_data.filter.strategy_type:
                query = query.where(
                    BacktestResultModel.strategy_type == input_data.filter.strategy_type
                )

        count_query = select(func.count()).select_from(query.subquery())
        total_result = await self.session.execute(count_query)
        total = total_result.scalar_one()

        sort_dir = desc if input_data.sort_dir == "desc" else asc
        if input_data.sort and input_data.sort in self.sortable_fields:
            query = query.order_by(
                sort_dir(getattr(BacktestResultModel, input_data.sort))
            )
        else:
            query = query.order_by(desc(BacktestResultModel.created_at))

        offset = (input_data.page - 1) * input_data.per_page
        query = query.offset(offset).limit(input_data.per_page)

        result = await self.session.execute(query)
        items = [_to_entity(model) for model in result.scalars().all()]

        return BacktestSearchOutput(
            items=items,
            total=total,
            current_page=input_data.page,
            per_page=input_data.per_page,
        )

    def get_entity(self) -> Type[BacktestResult]:
        return BacktestResult
