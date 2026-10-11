from typing import List, Optional, Set, Type

from sqlalchemy import delete, select, update
from sqlalchemy.ext.asyncio import AsyncSession
from trader.domain.ai_prediction import AIPrediction, AIPredictionId
from trader.domain.bot import BotId
from trader.domain.repositories.ai_prediction_repository import (
    AIPredictionSearchInput,
    AIPredictionSearchOutput,
    IAIPredictionRepository,
)
from trader.infra.db.sql_models import AIPredictionModel


def _to_model(entity: AIPrediction) -> AIPredictionModel:
    return AIPredictionModel(
        id=entity.id.value,
        bot_config_id=entity.bot_id.value,
        symbol=entity.symbol,
        ai_model_version=entity.ai_model_version,
        features_payload=entity.features_payload,
        prediction_signal=entity.prediction_signal,
        probability=entity.probability,
    )


def _to_entity(model: AIPredictionModel) -> AIPrediction:
    return AIPrediction(
        id=AIPredictionId(value=model.id),
        bot_id=BotId(value=model.bot_config_id),
        symbol=model.symbol,
        ai_model_version=model.ai_model_version,
        features_payload=model.features_payload,
        prediction_signal=model.prediction_signal,
        probability=float(model.probability),
    )


class AIPredictionPostgresRepository(IAIPredictionRepository):
    sortable_fields: List[str] = ["created_at", "probability"]

    def __init__(self, session: AsyncSession):
        self.session = session

    async def insert(self, entity: AIPrediction) -> AIPredictionId:
        model = _to_model(entity)
        self.session.add(model)
        await self.session.flush()
        return entity.id

    async def bulk_insert(self, entities: List[AIPrediction]) -> None:
        models = [_to_model(entity) for entity in entities]
        self.session.add_all(models)
        await self.session.flush()

    async def find_by_id(self, entity_id: AIPredictionId) -> Optional[AIPrediction]:
        result = await self.session.execute(
            select(AIPredictionModel).where(AIPredictionModel.id == entity_id.value)
        )
        model = result.scalar_one_or_none()
        return _to_entity(model) if model else None

    async def find_all(self) -> List[AIPrediction]:
        result = await self.session.execute(select(AIPredictionModel))
        return [_to_entity(model) for model in result.scalars().all()]

    async def find_by_ids(self, entity_ids: Set[AIPredictionId]) -> List[AIPrediction]:
        raw_ids = [eid.value for eid in entity_ids]
        result = await self.session.execute(
            select(AIPredictionModel).where(AIPredictionModel.id.in_(raw_ids))
        )
        return [_to_entity(model) for model in result.scalars().all()]

    async def update(self, entity: AIPrediction) -> None:
        await self.session.execute(
            update(AIPredictionModel)
            .where(AIPredictionModel.id == entity.id.value)
            .values(
                symbol=entity.symbol,
                ai_model_version=entity.ai_model_version,
                features_payload=entity.features_payload,
                prediction_signal=entity.prediction_signal,
                probability=entity.probability,
            )
        )

    async def delete(self, entity_id: AIPredictionId) -> None:
        await self.session.execute(
            delete(AIPredictionModel).where(AIPredictionModel.id == entity_id.value)
        )

    async def find_by_bot_id(
        self, bot_id: BotId, input_data: AIPredictionSearchInput
    ) -> AIPredictionSearchOutput:
        query = select(AIPredictionModel).where(
            AIPredictionModel.bot_config_id == bot_id.value
        )
        result = await self.session.execute(query)
        items = [_to_entity(model) for model in result.scalars().all()]
        return AIPredictionSearchOutput(
            items=items,
            total=len(items),
            current_page=input_data.page,
            per_page=input_data.per_page,
        )

    async def search(self, input_data: AIPredictionSearchInput) -> AIPredictionSearchOutput:
        query = select(AIPredictionModel)
        if input_data.filter and input_data.filter.bot_id:
            query = query.where(
                AIPredictionModel.bot_config_id == input_data.filter.bot_id.value
            )
        result = await self.session.execute(query)
        items = [_to_entity(model) for model in result.scalars().all()]
        return AIPredictionSearchOutput(
            items=items,
            total=len(items),
            current_page=input_data.page,
            per_page=input_data.per_page,
        )

    def get_entity(self) -> Type[AIPrediction]:
        return AIPrediction
