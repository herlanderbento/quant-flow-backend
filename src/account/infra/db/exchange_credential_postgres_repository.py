from ast import List
from typing import Optional, Type
import uuid
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.future import select
from sqlalchemy import func, update, delete
from account.domain.exchange_credential import ExchangeCredential, ExchangeCredentialId
from account.domain.exchange_credential_repository import (
    ExchangeCredentialSearchInput,
    ExchangeCredentialSearchOutput,
    IExchangeCredentialRepository,
)
from account.domain.user import UserId
from account.infra.db.sql_models import ExchangeCredentialModel
from shared.domain.search_input import SortDirection
from shared.utils.datetime_utils import to_aware_utc, to_naive_utc


def _to_model(exchange_credential: ExchangeCredential) -> ExchangeCredentialModel:
    return ExchangeCredentialModel(
        id=exchange_credential.id.value,
        user_id=exchange_credential.user_id.value,
        exchange_name=exchange_credential.exchange_name,
        api_key=exchange_credential.api_key,
        api_secret_encrypted=exchange_credential.api_secret_encrypted,
        is_testnet=exchange_credential.is_testnet,
        is_active=exchange_credential.is_active,
        created_at=to_naive_utc(exchange_credential.created_at),
        updated_at=to_naive_utc(exchange_credential.updated_at),
    )


def _to_entity(model: ExchangeCredentialModel) -> ExchangeCredential:
    return ExchangeCredential(
        id=ExchangeCredentialId(value=model.id),
        user_id=UserId(value=model.user_id),
        exchange_name=model.exchange_name,
        api_key=model.api_key,
        api_secret_encrypted=model.api_secret_encrypted,
        is_testnet=model.is_testnet,
        is_active=model.is_active,
        created_at=to_aware_utc(model.created_at),
        updated_at=to_aware_utc(model.updated_at),
    )


class ExchangeCredentialPostgresRepository(IExchangeCredentialRepository):
    sortable_fields = {"exchange_name", "is_testnet", "is_active", "created_at"}

    def __init__(self, session: AsyncSession):
        self.session = session

    async def insert(self, exchange_credential: ExchangeCredential) -> None:
        self.session.add(_to_model(exchange_credential))
        await self.session.commit()

    async def bulk_insert(self, exchange_credentials: List[ExchangeCredential]) -> None:
        self.session.add_all(exchange_credentials)
        await self.session.commit()

    async def find_by_id(self, id: uuid.UUID) -> Optional[ExchangeCredential]:
        result = await self.session.execute(
            select(ExchangeCredentialModel).where(ExchangeCredentialModel.id == id)
        )
        model = result.scalar_one_or_none()
        return _to_entity(model) if model else None

    async def find_all(self) -> List[ExchangeCredential]:
        models = await self.session.execute(select(ExchangeCredentialModel))
        return [_to_entity(model) for model in models.scalars().all()]

    async def find_by_ids(self, ids: List[uuid.UUID]) -> List[ExchangeCredential]:
        models = await self.session.execute(
            select(ExchangeCredentialModel).where(ExchangeCredentialModel.id.in_(ids))
        )
        return [_to_entity(model) for model in models.scalars().all()]

    async def find_by_user_id(
        self, user_id: UserId, props: ExchangeCredentialSearchInput
    ) -> ExchangeCredentialSearchOutput:
        query = select(ExchangeCredentialModel).where(
            ExchangeCredentialModel.user_id == user_id
        )

        if props.filter:
            if props.filter.exchange_name:
                query = query.where(
                    ExchangeCredentialModel.exchange_name == props.filter.exchange_name
                )
            if props.filter.is_testnet:
                query = query.where(
                    ExchangeCredentialModel.is_testnet == props.filter.is_testnet
                )
            if props.filter.is_active is not None:
                query = query.where(
                    ExchangeCredentialModel.is_active == props.filter.is_active
                )

        total_query = select(func.count()).select_from(query.subquery())

        total = (await self.session.execute(total_query)).scalar_one()

        if props.sort and props.sort in self.sortable_fields:
            sort_col = getattr(ExchangeCredentialModel, props.sort)
            if props.sort_dir == SortDirection.DESC:
                query = query.order_by(sort_col.desc())
            else:
                query = query.order_by(sort_col.asc())
        else:
            query = query.order_by(ExchangeCredentialModel.created_at.desc())

        query = query.offset((props.page - 1) * props.per_page).limit(props.per_page)

        models = await self.session.execute(query)

        items = [_to_entity(model) for model in models.scalars().all()]

        return ExchangeCredentialSearchOutput(
            items=items,
            total=total,
            current_page=props.page,
            per_page=props.per_page,
        )

    async def find_by_user_exchange(
        self, user_id: UserId, exchange_name: str, is_testnet: bool
    ) -> Optional[ExchangeCredential]:
        result = await self.session.execute(
            select(ExchangeCredentialModel).where(
                ExchangeCredentialModel.user_id == user_id,
                ExchangeCredentialModel.exchange_name == exchange_name,
                ExchangeCredentialModel.is_testnet == is_testnet,
            )
        )
        model = result.scalar_one_or_none()
        return _to_entity(model) if model else None

    async def search(
        self, props: ExchangeCredentialSearchInput
    ) -> ExchangeCredentialSearchOutput:
        query = select(ExchangeCredentialModel)

        if props.filter:
            if props.filter.exchange_name:
                query = query.where(
                    ExchangeCredentialModel.exchange_name.ilike(
                        f"%{props.filter.exchange_name}%"
                    )
                )
            if props.filter.is_testnet is not None:
                query = query.where(
                    ExchangeCredentialModel.is_testnet == props.filter.is_testnet
                )
            if props.filter.is_active is not None:
                query = query.where(
                    ExchangeCredentialModel.is_active == props.filter.is_active
                )

        total_query = select(func.count()).select_from(query.subquery())
        total = (await self.session.execute(total_query)).scalar_one()

        if props.sort and props.sort in self.sortable_fields:
            sort_col = getattr(ExchangeCredentialModel, props.sort)
            if props.sort_dir == SortDirection.DESC:
                query = query.order_by(sort_col.desc())
            else:
                query = query.order_by(sort_col.asc())
        else:
            query = query.order_by(ExchangeCredentialModel.created_at.desc())

        query = query.offset((props.page - 1) * props.per_page).limit(props.per_page)

        models = await self.session.execute(query)

        items = [_to_entity(model) for model in models.scalars().all()]

        return ExchangeCredentialSearchOutput(
            items=items,
            total=total,
            current_page=props.page,
            per_page=props.per_page,
        )

    async def update(self, exchange_credential: ExchangeCredential) -> None:
        await self.session.execute(
            update(ExchangeCredentialModel)
            .where(ExchangeCredentialModel.id == exchange_credential.id.value)
            .values(
                exchange_name=exchange_credential.exchange_name,
                api_key=exchange_credential.api_key,
                api_secret_encrypted=exchange_credential.api_secret_encrypted,
                is_testnet=exchange_credential.is_testnet,
                is_active=exchange_credential.is_active,
                updated_at=to_naive_utc(exchange_credential.updated_at),
            )
        )
        await self.session.commit()

    async def delete(self, id: uuid.UUID) -> None:
        await self.session.execute(
            delete(ExchangeCredentialModel).where(ExchangeCredentialModel.id == id)
        )
        await self.session.commit()

    def get_entity(self) -> Type[ExchangeCredential]:
        return ExchangeCredential
