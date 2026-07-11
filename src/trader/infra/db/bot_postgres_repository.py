from typing import List, Optional, Set, Type

from sqlalchemy.ext.asyncio import AsyncSession

from sqlalchemy.future import select

from sqlalchemy import delete, update, func, asc, desc


from account.domain.user import UserId

from account.domain.credential import CredentialId

from trader.domain.bot import Bot, BotId

from trader.domain.repositories.bot_repository import (
    BotSearchInput,
    BotSearchOutput,
    IBotRepository,
)

from trader.infra.db.sql_models import BotConfigModel


def _to_model(entity: Bot) -> BotConfigModel:

    return BotConfigModel(
        id=entity.id.value,
        user_id=entity.user_id.value,
        credential_id=entity.credential_id.value,
        name=entity.name,
        symbol=entity.symbol,
        strategy_type=entity.strategy_type,
        is_active=entity.is_active,
        allocated_capital=entity.allocated_capital,
        stop_loss_pct=entity.stop_loss_pct,
        take_profit_pct=entity.take_profit_pct,
        created_at=entity.created_at,
        updated_at=entity.updated_at,
    )


def _to_entity(model: BotConfigModel) -> Bot:

    return Bot(
        id=BotId(str(model.id)),
        user_id=UserId(str(model.user_id)),
        credential_id=CredentialId(str(model.credential_id)),
        name=model.name,
        symbol=model.symbol,
        strategy_type=model.strategy_type,
        is_active=model.is_active,
        allocated_capital=model.allocated_capital,
        stop_loss_pct=model.stop_loss_pct,
        take_profit_pct=model.take_profit_pct,
        created_at=model.created_at,
        updated_at=model.updated_at,
    )


class BotPostgresRepository(IBotRepository):

    sortable_fields: List[str] = [
        "name",
        "created_at",
        "allocated_capital",
        "is_active",
    ]

    def __init__(self, session: AsyncSession):

        self.session = session

    async def insert(self, entity: Bot) -> None:

        model = _to_model(entity)

        self.session.add(model)

        await self.session.flush()

    async def bulk_insert(self, entities: List[Bot]) -> None:

        models = [_to_model(entity) for entity in entities]

        self.session.add_all(models)

        await self.session.flush()

    async def find_by_id(self, entity_id: BotId) -> Optional[Bot]:

        result = await self.session.execute(
            select(BotConfigModel).where(BotConfigModel.id == entity_id.value)
        )

        model = result.scalar_one_or_none()

        if not model:

            return None

        return _to_entity(model)

    async def find_all(self) -> List[Bot]:

        result = await self.session.execute(select(BotConfigModel))

        return [_to_entity(model) for model in result.scalars().all()]

    async def find_by_ids(self, entity_ids: Set[BotId]) -> List[Bot]:

        raw_ids = [eid.value for eid in entity_ids]

        result = await self.session.execute(
            select(BotConfigModel).where(BotConfigModel.id.in_(raw_ids))
        )

        return [_to_entity(model) for model in result.scalars().all()]

    async def update(self, entity: Bot) -> None:

        await self.session.execute(
            update(BotConfigModel)
            .where(BotConfigModel.id == entity.id.value)
            .values(
                name=entity.name,
                symbol=entity.symbol,
                strategy_type=entity.strategy_type,
                is_active=entity.is_active,
                allocated_capital=entity.allocated_capital,
                stop_loss_pct=entity.stop_loss_pct,
                take_profit_pct=entity.take_profit_pct,
                updated_at=entity.updated_at,
            )
        )

    async def delete(self, entity_id: BotId) -> None:

        await self.session.execute(
            delete(BotConfigModel).where(BotConfigModel.id == entity_id.value)
        )

    async def find_by_user_id(
        self, user_id: UserId, input_data: BotSearchInput
    ) -> BotSearchOutput:

        query = select(BotConfigModel).where(BotConfigModel.user_id == user_id.value)

        return await self._execute_search(query, input_data)

    async def search(self, input_data: BotSearchInput) -> BotSearchOutput:

        query = select(BotConfigModel)

        return await self._execute_search(query, input_data)

    async def _execute_search(
        self, base_query, input_data: BotSearchInput
    ) -> BotSearchOutput:

        query = base_query

        if input_data.filter:

            if input_data.filter.name:

                query = query.where(
                    BotConfigModel.name.ilike(f"%{input_data.filter.name}%")
                )

            if input_data.filter.strategy_type:

                query = query.where(
                    BotConfigModel.strategy_type == input_data.filter.strategy_type
                )

            if input_data.filter.is_active is not None:

                query = query.where(
                    BotConfigModel.is_active == input_data.filter.is_active
                )

        count_query = select(func.count()).select_from(query.subquery())

        total_result = await self.session.execute(count_query)

        total = total_result.scalar_one()

        sort_dir = desc if input_data.sort_dir == "desc" else asc

        if input_data.sort and input_data.sort in self.sortable_fields:

            query = query.order_by(sort_dir(getattr(BotConfigModel, input_data.sort)))

        else:

            query = query.order_by(desc(BotConfigModel.created_at))

        offset = (input_data.page - 1) * input_data.per_page

        query = query.offset(offset).limit(input_data.per_page)

        result = await self.session.execute(query)

        items = [_to_entity(model) for model in result.scalars().all()]

        return BotSearchOutput(
            items=items,
            total=total,
            current_page=input_data.page,
            per_page=input_data.per_page,
        )

    async def find_active(self) -> List[Bot]:
        result = await self.session.execute(
            select(BotConfigModel).where(BotConfigModel.is_active.is_(True))
        )
        return [_to_entity(model) for model in result.scalars().all()]

    def get_entity(self) -> Type[Bot]:

        return Bot
