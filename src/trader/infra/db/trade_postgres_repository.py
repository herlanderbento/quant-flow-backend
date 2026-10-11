from typing import List, Optional, Set, Type

from sqlalchemy import asc, delete, desc, func, select, update
from sqlalchemy.ext.asyncio import AsyncSession

from account.domain.credential import CredentialId
from account.domain.user import UserId
from trader.domain.ai_prediction import AIPredictionId
from trader.domain.bot import BotId
from trader.domain.repositories.trade_repository import (
    ITradeRepository,
    TradeSearchInput,
    TradeSearchOutput,
)
from trader.domain.trade import (
    ACTIVE_TRADE_STATUSES,
    TRADE_STATUS_CANCELLED,
    TRADE_STATUS_CLOSED,
    TRADE_STATUS_OPEN,
    TRADE_STATUS_PENDING_CLOSE,
    Trade,
    TradeId,
)
from trader.infra.db.sql_models import BotConfigModel, TradeModel


def _to_model(entity: Trade) -> TradeModel:
    return TradeModel(
        id=entity.id.value,
        bot_config_id=entity.bot_id.value,
        ai_prediction_id=(
            entity.ai_prediction_id.value
            if entity.ai_prediction_id is not None
            else None
        ),
        symbol=entity.symbol,
        side=entity.side,
        status=entity.status,
        client_order_id=entity.client_order_id,
        entry_context=entity.entry_context,
        price_executed=entity.price_executed,
        quantity=entity.quantity,
        open_quantity=entity.open_quantity,
        entry_cost=entity.entry_cost,
        pnl_usd=entity.pnl_usd,
        pnl_pct=entity.pnl_pct,
        fee_paid=entity.fee_paid,
        exchange_order_id=entity.exchange_order_id,
        exit_client_order_id=entity.exit_client_order_id,
        exit_order_id=entity.exit_order_id,
        exit_price=entity.exit_price,
        exit_reason=entity.exit_reason,
        executed_at=entity.executed_at,
        updated_at=entity.updated_at,
        closed_at=entity.closed_at,
    )


def _float_or_none(value) -> float | None:
    # asyncpg returns Numeric columns as Decimal; the domain works with float.
    return float(value) if value is not None else None


def _to_entity(model: TradeModel) -> Trade:
    return Trade(
        id=TradeId(value=model.id),
        bot_id=BotId(value=model.bot_config_id),
        ai_prediction_id=(
            AIPredictionId(value=model.ai_prediction_id)
            if model.ai_prediction_id is not None
            else None
        ),
        symbol=model.symbol,
        side=model.side,
        status=model.status,
        client_order_id=model.client_order_id,
        entry_context=model.entry_context,
        price_executed=_float_or_none(model.price_executed),
        quantity=float(model.quantity),
        open_quantity=_float_or_none(model.open_quantity),
        entry_cost=_float_or_none(model.entry_cost),
        pnl_usd=_float_or_none(model.pnl_usd),
        pnl_pct=_float_or_none(model.pnl_pct),
        fee_paid=_float_or_none(model.fee_paid),
        exchange_order_id=model.exchange_order_id,
        exit_client_order_id=model.exit_client_order_id,
        exit_order_id=model.exit_order_id,
        exit_price=_float_or_none(model.exit_price),
        exit_reason=model.exit_reason,
        executed_at=model.executed_at,
        updated_at=model.updated_at or model.executed_at,
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
            select(TradeModel).where(TradeModel.id == entity_id.value)
        )
        model = result.scalar_one_or_none()
        return _to_entity(model) if model else None

    async def find_all(self) -> List[Trade]:
        result = await self.session.execute(select(TradeModel))
        return [_to_entity(model) for model in result.scalars().all()]

    async def find_by_ids(self, entity_ids: Set[TradeId]) -> List[Trade]:
        raw_ids = [eid.value for eid in entity_ids]
        result = await self.session.execute(
            select(TradeModel).where(TradeModel.id.in_(raw_ids))
        )
        return [_to_entity(model) for model in result.scalars().all()]

    async def update(self, entity: Trade) -> None:
        await self.session.execute(
            update(TradeModel)
            .where(TradeModel.id == entity.id.value)
            .values(
                status=entity.status,
                price_executed=entity.price_executed,
                quantity=entity.quantity,
                open_quantity=entity.open_quantity,
                entry_cost=entity.entry_cost,
                pnl_usd=entity.pnl_usd,
                pnl_pct=entity.pnl_pct,
                fee_paid=entity.fee_paid,
                exchange_order_id=entity.exchange_order_id,
                exit_client_order_id=entity.exit_client_order_id,
                exit_order_id=entity.exit_order_id,
                exit_price=entity.exit_price,
                exit_reason=entity.exit_reason,
                executed_at=entity.executed_at,
                updated_at=entity.updated_at,
                closed_at=entity.closed_at,
            )
        )

    async def delete(self, entity_id: TradeId) -> None:
        await self.session.execute(
            delete(TradeModel).where(TradeModel.id == entity_id.value)
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

    async def find_active_by_bot_id(self, bot_id: BotId) -> list[Trade]:
        result = await self.session.execute(
            select(TradeModel).where(
                TradeModel.bot_config_id == bot_id.value,
                TradeModel.status.in_(ACTIVE_TRADE_STATUSES),
            )
        )
        return [_to_entity(model) for model in result.scalars().all()]

    async def find_latest_final_by_bot_id(self, bot_id: BotId) -> Optional[Trade]:
        result = await self.session.execute(
            select(TradeModel)
            .where(
                TradeModel.bot_config_id == bot_id.value,
                TradeModel.status.in_((TRADE_STATUS_CLOSED, TRADE_STATUS_CANCELLED)),
                TradeModel.closed_at.is_not(None),
            )
            .order_by(desc(TradeModel.closed_at))
            .limit(1)
        )
        model = result.scalar_one_or_none()
        return _to_entity(model) if model else None

    async def realized_pnls(self, bot_id: BotId) -> list[tuple]:
        result = await self.session.execute(
            select(TradeModel.closed_at, TradeModel.pnl_usd)
            .where(
                TradeModel.bot_config_id == bot_id.value,
                TradeModel.status == TRADE_STATUS_CLOSED,
                TradeModel.pnl_usd.is_not(None),
                TradeModel.closed_at.is_not(None),
            )
            .order_by(asc(TradeModel.closed_at))
        )
        return [(closed_at, float(pnl)) for closed_at, pnl in result.all()]

    async def open_base_quantity(self, credential_id: CredentialId, base_asset: str) -> float:
        result = await self.session.execute(
            select(func.coalesce(func.sum(func.coalesce(TradeModel.open_quantity, TradeModel.quantity)), 0))
            .join(BotConfigModel, TradeModel.bot_config_id == BotConfigModel.id)
            .where(
                BotConfigModel.credential_id == credential_id.value,
                TradeModel.symbol.like(f"{base_asset}/%"),
                TradeModel.status.in_((TRADE_STATUS_OPEN, TRADE_STATUS_PENDING_CLOSE)),
            )
        )
        return float(result.scalar_one())

    async def active_exposure_by_user(self, user_id: UserId) -> float:
        result = await self.session.execute(
            select(
                func.coalesce(
                    func.sum(
                        func.coalesce(TradeModel.entry_cost, BotConfigModel.allocated_capital)
                    ),
                    0,
                )
            )
            .join(BotConfigModel, TradeModel.bot_config_id == BotConfigModel.id)
            .where(
                BotConfigModel.user_id == user_id.value,
                TradeModel.status.in_(ACTIVE_TRADE_STATUSES),
            )
        )
        return float(result.scalar_one())

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
