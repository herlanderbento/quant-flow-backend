from datetime import date, datetime, timezone
from typing import List, Optional, Set, Type
import uuid

from sqlalchemy import delete, select, update
from sqlalchemy.ext.asyncio import AsyncSession

from account.domain.user import UserId
from wallet.domain.repositories.wallet_repository import IWalletRepository
from wallet.domain.wallet import Wallet, WalletId
from wallet.infra.db.sql_models import WalletModel
from shared.utils.datetime_utils import to_aware_utc, to_naive_utc


def _to_model(entity: Wallet) -> WalletModel:
    return WalletModel(
        id=entity.id.value,
        user_id=entity.user_id.value,
        asset=entity.asset,
        free_balance=entity.free_balance,
        locked_balance=entity.locked_balance,
        updated_at=to_naive_utc(entity.updated_at),
    )


def _to_entity(model: WalletModel) -> Wallet:
    return Wallet(
        id=WalletId(value=model.id),
        user_id=UserId(value=model.user_id),
        asset=model.asset,
        free_balance=float(model.free_balance),
        locked_balance=float(model.locked_balance),
        updated_at=to_aware_utc(model.updated_at),
    )


class WalletPostgresRepository(IWalletRepository):
    def __init__(self, session: AsyncSession):
        self.session = session

    async def insert(self, entity: Wallet) -> None:
        self.session.add(_to_model(entity))
        await self.session.flush()

    async def bulk_insert(self, entities: List[Wallet]) -> None:
        self.session.add_all([_to_model(entity) for entity in entities])
        await self.session.flush()

    async def find_by_id(self, entity_id: WalletId) -> Optional[Wallet]:
        result = await self.session.execute(
            select(WalletModel).where(WalletModel.id == entity_id.value)
        )
        model = result.scalar_one_or_none()
        return _to_entity(model) if model else None

    async def find_all(self) -> List[Wallet]:
        result = await self.session.execute(select(WalletModel))
        return [_to_entity(model) for model in result.scalars().all()]

    async def find_by_ids(self, entity_ids: Set[WalletId]) -> List[Wallet]:
        raw_ids = [entity_id.value for entity_id in entity_ids]
        result = await self.session.execute(
            select(WalletModel).where(WalletModel.id.in_(raw_ids))
        )
        return [_to_entity(model) for model in result.scalars().all()]

    async def update(self, entity: Wallet) -> None:
        await self.session.execute(
            update(WalletModel)
            .where(WalletModel.id == entity.id.value)
            .values(
                free_balance=entity.free_balance,
                locked_balance=entity.locked_balance,
                updated_at=to_naive_utc(entity.updated_at),
            )
        )

    async def delete(self, entity_id: WalletId) -> None:
        await self.session.execute(
            delete(WalletModel).where(WalletModel.id == entity_id.value)
        )

    async def find_by_user_id(self, user_id: UserId) -> list[Wallet]:
        result = await self.session.execute(
            select(WalletModel).where(WalletModel.user_id == user_id.value)
        )
        return [_to_entity(model) for model in result.scalars().all()]

    async def upsert_by_user_asset(
        self,
        user_id: UserId,
        asset: str,
        free_balance: float,
        locked_balance: float,
    ) -> Wallet:
        result = await self.session.execute(
            select(WalletModel).where(
                WalletModel.user_id == user_id.value,
                WalletModel.asset == asset,
            )
        )
        model = result.scalar_one_or_none()
        if model:
            wallet = _to_entity(model)
            wallet.update_balances(free_balance, locked_balance)
            await self.update(wallet)
            return wallet

        wallet = Wallet(
            user_id=user_id,
            asset=asset,
            free_balance=free_balance,
            locked_balance=locked_balance,
            updated_at=datetime.now(timezone.utc),
        )
        wallet.validate()
        await self.insert(wallet)
        return wallet

    def get_entity(self) -> Type[Wallet]:
        return Wallet
