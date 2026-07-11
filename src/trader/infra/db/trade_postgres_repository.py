from typing import List, Optional, Set, Type

from sqlalchemy import asc, delete, desc, func, select, update
from sqlalchemy.ext.asyncio import AsyncSession

from account.domain.user import UserId
from trader.domain.ai_prediction import AIPredictionId
from trader.domain.bot import BotId
from trader.domain.repositories.trade_repository import (
    ITradeRepository,
    TradeSearchInput,
    TradeSearchOutput,
)
from trader.domain.trade import TRADE_STATUS_OPEN, Trade, TradeId
from trader.infra.db.sql_models import BotConfigModel, TradeModel


def _to_model(entity: Trade) -> TradeModel:
    return TradeModel(
        id=entity.id,
        bot_config_id=entity.bot_id.value,
        ai_prediction_id=entity.ai_prediction_id,
        symbol=entity.symbol,
        side=entity.side,
        status=entity.status,
        price_executed=entity.price_executed,
        quantity=entity.quantity,
        pnl_usd=entity.pnl_usd,
        pnl_pct=entity.pnl_pct,
        fee_paid=entity.fee_paid,
        exchange_order_id=entity.exchange_order_id,
        executed_at=entity.executed_at,
        closed_at=entity.closed_at,
    )


def _to_entity(model: TradeModel) -> Trade:
    return Trade(
        id=TradeId(model.id),
        bot_id=BotId(str(model.bot_config_id)),
        ai_prediction_id=(
            AIPredictionId(model.ai_prediction_id)
            if model.ai_prediction_id is not None
            else None
        ),
        symbol=model.symbol,
        side=model.side,
        status=model.status,
        price_executed=float(model.price_executed),
        quantity=float(model.quantity),
        pnl_usd=float(model.pnl_usd) if model.pnl_usd is not None else None,
        pnl_pct=float(model.pnl_pct) if model.pnl_pct is not None else None,
        fee_paid=float(model.fee_paid) if model.fee_paid is not None else None,
        exchange_order_id=model.exchange_order_id,
        executed_at=model.executed_at,
        closed_at=model.closed_at,
    )


class TradePostgresRepository(ITradeRepository):
    sortable_fields: List[str] = ["executed_at", "symbol", "status", "side"]

    def __init__(self, session: AsyncSession):
        self.session = session

    async def insert(self, entity: Trade) -> None:
        self.session.add(_to_model(entity))
        await self.session.flush()

    async def bulk_insert(self, entities: List[Trade]) -> None:
        self.session.add_all([_to_model(entity) for entity in entities])
        await self.session.flush()

    async def find_by_id(self, entity_id: TradeId) -> Optional[Trade]:
        result = await self.session.execute(
            select(TradeModel).where(TradeModel.id == entity_id)
        )
        model = result.scalar_one_or_none()
        return _to_entity(model) if model else None

    async def find_all(self) -> List[Trade]:
        result = await self.session.execute(select(TradeModel))
        return [_to_entity(model) for model in result.scalars().all()]

    async def find_by_ids(self, entity_ids: Set[TradeId]) -> List[Trade]:
        raw_ids = list(entity_ids)
        result = await self.session.execute(
            select(TradeModel).where(TradeModel.id.in_(raw_ids))
        )
        return [_to_entity(model) for model in result.scalars().all()]

    async def update(self, entity: Trade) -> None:
        await self.session.execute(
            update(TradeModel)
            .where(TradeModel.id == entity.id)
            .values(
                status=entity.status,
                pnl_usd=entity.pnl_usd,
                pnl_pct=entity.pnl_pct,
                fee_paid=entity.fee_paid,
                closed_at=entity.closed_at,
            )
        )

    async def delete(self, entity_id: TradeId) -> None:
        await self.session.execute(
            delete(TradeModel).where(TradeModel.id == entity_id)
        )

    async def find_by_user_id(
        self, user_id: UserId, input_data: TradeSearchInput
    ) -> TradeSearchOutput:
        query = (
            select(TradeModel)
            .join(BotConfigModel, TradeModel.bot_config_id == BotConfigModel.id)
            .where(BotConfigModel.user_id == user_id.value)
        )
        return await self._execute_search(query, input_data)

    async def find_open_by_bot_id(self, bot_id: BotId) -> list[Trade]:
        result = await self.session.execute(
            select(TradeModel).where(
                TradeModel.bot_config_id == bot_id.value,
                TradeModel.status == TRADE_STATUS_OPEN,
            )
        )
        return [_to_entity(model) for model in result.scalars().all()]

    async def _execute_search(
        self, base_query, input_data: TradeSearchInput
    ) -> TradeSearchOutput:
        query = base_query

        if input_data.filter:
            if input_data.filter.bot_id:
                query = query.where(
                    TradeModel.bot_config_id == input_data.filter.bot_id.value
                )
            if input_data.filter.symbol:
                query = query.where(TradeModel.symbol == input_data.filter.symbol)
            if input_data.filter.status:
                query = query.where(TradeModel.status == input_data.filter.status)
            if input_data.filter.side:
                query = query.where(TradeModel.side == input_data.filter.side)

        count_query = select(func.count()).select_from(query.subquery())
        total_result = await self.session.execute(count_query)
        total = total_result.scalar_one()

        sort_dir = desc if input_data.sort_dir == "desc" else asc
        if input_data.sort and input_data.sort in self.sortable_fields:
            query = query.order_by(sort_dir(getattr(TradeModel, input_data.sort)))
        else:
            query = query.order_by(desc(TradeModel.executed_at))

        offset = (input_data.page - 1) * input_data.per_page
        query = query.offset(offset).limit(input_data.per_page)

        result = await self.session.execute(query)
        items = [_to_entity(model) for model in result.scalars().all()]

        return TradeSearchOutput(
            items=items,
            total=total,
            current_page=input_data.page,
            per_page=input_data.per_page,
        )

    def get_entity(self) -> Type[Trade]:
        return Trade
