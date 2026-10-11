from typing import List, Optional, Type
import uuid
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.future import select
from sqlalchemy import delete, func, update

from account.domain.user import User, UserId
from account.domain.user_repository import (
    IUserRepository,
    UserSearchInput,
    UserSearchOutput,
)
from account.infra.db.sql_models import UserModel
from shared.domain.search_input import SortDirection
from shared.utils.datetime_utils import to_aware_utc, to_naive_utc


def _to_model(user: User) -> UserModel:
    return UserModel(
        id=user.id.value,
        name=user.name,
        email=user.email,
        password=user.password,
        is_active=user.is_active,
        created_at=to_naive_utc(user.created_at),
        updated_at=to_naive_utc(user.updated_at),
    )


def _to_entity(model: UserModel) -> User:
    return User(
        id=UserId(value=model.id),
        name=model.name,
        email=model.email,
        password=model.password,
        is_active=model.is_active,
        created_at=to_aware_utc(model.created_at),
        updated_at=to_aware_utc(model.updated_at),
    )


class UserPostgresRepository(IUserRepository):
    sortable_fields = {"name", "email", "created_at", "is_active"}

    def __init__(self, session: AsyncSession):
        self.session = session

    async def insert(self, entity: User) -> None:
        self.session.add(_to_model(entity))
        await self.session.commit()

    async def bulk_insert(self, entities: List[User]) -> None:
        self.session.add_all(entities)
        await self.session.commit()

    async def find_by_id(self, id: uuid.UUID) -> Optional[User]:
        result = await self.session.execute(select(UserModel).where(UserModel.id == id))
        model = result.scalar_one_or_none()
        return _to_entity(model) if model else None

    async def find_all(self) -> List[User]:
        models = await self.session.execute(select(UserModel))
        return [_to_entity(model) for model in models.scalars().all()]

    async def find_by_ids(self, ids: List[uuid.UUID]) -> List[User]:
        models = await self.session.execute(
            select(UserModel).where(UserModel.id.in_(ids))
        )
        return [_to_entity(model) for model in models.scalars().all()]

    async def find_by_email(self, email: str) -> Optional[User]:
        result = await self.session.execute(
            select(UserModel).where(UserModel.email == email)
        )
        model = result.scalar_one_or_none()
        return _to_entity(model) if model else None

    async def search(self, props: UserSearchInput) -> UserSearchOutput:
        query = select(UserModel)

        if props.filter:
            if props.filter.id:
                query = query.where(UserModel.id == props.filter.id)
            if props.filter.name:
                query = query.where(UserModel.name.ilike(f"%{props.filter.name}%"))
            if props.filter.email:
                query = query.where(UserModel.email.ilike(f"%{props.filter.email}%"))
            if props.filter.is_active is not None:
                query = query.where(UserModel.is_active == props.filter.is_active)

        total_query = select(func.count()).select_from(query.subquery())
        total = (await self.session.execute(total_query)).scalar_one()

        if props.sort and props.sort in self.sortable_fields:
            sort_col = getattr(UserModel, props.sort)
            if props.sort_dir == SortDirection.DESC:
                query = query.order_by(sort_col.desc())
            else:
                query = query.order_by(sort_col.asc())
        else:
            query = query.order_by(UserModel.created_at.desc())

        query = query.offset((props.page - 1) * props.per_page).limit(props.per_page)
        models = await self.session.execute(query)
        items = [_to_entity(model) for model in models.scalars().all()]

        return UserSearchOutput(
            items=items,
            total=total,
            current_page=props.page,
            per_page=props.per_page,
        )

    async def update(self, entity: User) -> None:
        await self.session.execute(
            update(UserModel)
            .where(UserModel.id == entity.id.value)
            .values(
                name=entity.name,
                email=entity.email,
                password=entity.password,
                is_active=entity.is_active,
                updated_at=to_naive_utc(entity.updated_at),
            )
        )
        await self.session.commit()

    async def delete(self, id: uuid.UUID) -> None:
        await self.session.execute(delete(UserModel).where(UserModel.id == id))
        await self.session.commit()

    def get_entity(self) -> Type[User]:
        return User
