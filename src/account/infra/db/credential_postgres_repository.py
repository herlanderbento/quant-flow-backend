from typing import List, Optional, Type
import uuid
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.future import select
from sqlalchemy import func, update, delete
from account.domain.credential import Credential, CredentialId
from account.domain.credential_repository import (
    CredentialSearchInput,
    CredentialSearchOutput,
    ICredentialRepository,
)
from account.domain.user import UserId
from account.infra.db.sql_models import CredentialModel
from shared.domain.search_input import SortDirection
from shared.utils.datetime_utils import to_aware_utc, to_naive_utc


def _to_model(credential: Credential) -> CredentialModel:
    return CredentialModel(
        id=credential.id.value,
        user_id=credential.user_id.value,
        name=credential.name,
        api_key=credential.api_key,
        api_key_hint=credential.api_key_hint,
        api_secret=credential.api_secret,
        is_testnet=credential.is_testnet,
        is_active=credential.is_active,
        created_at=to_naive_utc(credential.created_at),
        updated_at=to_naive_utc(credential.updated_at),
    )


def _to_entity(model: CredentialModel) -> Credential:
    return Credential(
        id=CredentialId(value=model.id),
        user_id=UserId(value=model.user_id),
        name=model.name,
        api_key=model.api_key,
        api_key_hint=model.api_key_hint,
        api_secret=model.api_secret,
        is_testnet=model.is_testnet,
        is_active=model.is_active,
        created_at=to_aware_utc(model.created_at),
        updated_at=to_aware_utc(model.updated_at),
    )


class CredentialPostgresRepository(ICredentialRepository):
    sortable_fields = {"name", "is_testnet", "is_active", "created_at"}

    def __init__(self, session: AsyncSession):
        self.session = session

    async def insert(self, entity: Credential) -> None:
        self.session.add(_to_model(entity))
        await self.session.commit()

    async def bulk_insert(self, entities: List[Credential]) -> None:
        self.session.add_all(entities)
        await self.session.commit()

    async def find_by_id(self, id: uuid.UUID) -> Optional[Credential]:
        result = await self.session.execute(
            select(CredentialModel).where(CredentialModel.id == id)
        )
        model = result.scalar_one_or_none()
        return _to_entity(model) if model else None

    async def find_all(self) -> List[Credential]:
        models = await self.session.execute(select(CredentialModel))
        return [_to_entity(model) for model in models.scalars().all()]

    async def find_by_ids(self, ids: List[uuid.UUID]) -> List[Credential]:
        models = await self.session.execute(
            select(CredentialModel).where(CredentialModel.id.in_(ids))
        )
        return [_to_entity(model) for model in models.scalars().all()]

    async def find_by_user_id(
        self, user_id: UserId, props: CredentialSearchInput
    ) -> CredentialSearchOutput:
        query = select(CredentialModel).where(
            CredentialModel.user_id == user_id
        )

        if props.filter:
            if props.filter.name:
                query = query.where(
                    CredentialModel.name == props.filter.name
                )
            if props.filter.is_testnet:
                query = query.where(
                    CredentialModel.is_testnet == props.filter.is_testnet
                )
            if props.filter.is_active is not None:
                query = query.where(
                    CredentialModel.is_active == props.filter.is_active
                )

        total_query = select(func.count()).select_from(query.subquery())

        total = (await self.session.execute(total_query)).scalar_one()

        if props.sort and props.sort in self.sortable_fields:
            sort_col = getattr(CredentialModel, props.sort)
            if props.sort_dir == SortDirection.DESC:
                query = query.order_by(sort_col.desc())
            else:
                query = query.order_by(sort_col.asc())
        else:
            query = query.order_by(CredentialModel.created_at.desc())

        query = query.offset((props.page - 1) * props.per_page).limit(props.per_page)

        models = await self.session.execute(query)

        items = [_to_entity(model) for model in models.scalars().all()]

        return CredentialSearchOutput(
            items=items,
            total=total,
            current_page=props.page,
            per_page=props.per_page,
        )

    async def find_active_by_user(
        self, user_id: UserId, name: str, is_testnet: bool
    ) -> List[Credential]:
        result = await self.session.execute(
            select(CredentialModel).where(
                CredentialModel.user_id == user_id,
                CredentialModel.name == name,
                CredentialModel.is_testnet == is_testnet,
                CredentialModel.is_active.is_(True),
            )
        )
        return [_to_entity(model) for model in result.scalars().all()]

    async def search(
        self, props: CredentialSearchInput
    ) -> CredentialSearchOutput:
        query = select(CredentialModel)

        if props.filter:
            if props.filter.name:
                query = query.where(
                    CredentialModel.name.ilike(
                        f"%{props.filter.name}%"
                    )
                )
            if props.filter.is_testnet is not None:
                query = query.where(
                    CredentialModel.is_testnet == props.filter.is_testnet
                )
            if props.filter.is_active is not None:
                query = query.where(
                    CredentialModel.is_active == props.filter.is_active
                )

        total_query = select(func.count()).select_from(query.subquery())
        total = (await self.session.execute(total_query)).scalar_one()

        if props.sort and props.sort in self.sortable_fields:
            sort_col = getattr(CredentialModel, props.sort)
            if props.sort_dir == SortDirection.DESC:
                query = query.order_by(sort_col.desc())
            else:
                query = query.order_by(sort_col.asc())
        else:
            query = query.order_by(CredentialModel.created_at.desc())

        query = query.offset((props.page - 1) * props.per_page).limit(props.per_page)

        models = await self.session.execute(query)

        items = [_to_entity(model) for model in models.scalars().all()]

        return CredentialSearchOutput(
            items=items,
            total=total,
            current_page=props.page,
            per_page=props.per_page,
        )

    async def update(self, entity: Credential) -> None:
        await self.session.execute(
            update(CredentialModel)
            .where(CredentialModel.id == entity.id.value)
            .values(
                name=entity.name,
                api_key=entity.api_key,
                api_key_hint=entity.api_key_hint,
                api_secret=entity.api_secret,
                is_testnet=entity.is_testnet,
                is_active=entity.is_active,
                updated_at=to_naive_utc(entity.updated_at),
            )
        )
        await self.session.commit()

    async def delete(self, id: uuid.UUID) -> None:
        await self.session.execute(
            delete(CredentialModel).where(CredentialModel.id == id)
        )
        await self.session.commit()

    def get_entity(self) -> Type[Credential]:
        return Credential
