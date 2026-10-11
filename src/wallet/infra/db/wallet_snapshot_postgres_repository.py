from datetime import date, datetime, timezone
from typing import Optional

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from account.domain.user import UserId
from wallet.domain.repositories.wallet_snapshot_repository import IWalletSnapshotRepository
from wallet.domain.wallet_snapshot import WalletSnapshot, WalletSnapshotId
from wallet.infra.db.sql_models import WalletSnapshotModel
from shared.utils.datetime_utils import to_aware_utc, to_naive_utc


def _to_model(entity: WalletSnapshot) -> WalletSnapshotModel:
    return WalletSnapshotModel(
        id=entity.id.value,
        user_id=entity.user_id.value,
        total_equity_usdt=entity.total_equity_usdt,
        snapshot_date=entity.snapshot_date,
        created_at=to_naive_utc(entity.created_at),
    )


def _to_entity(model: WalletSnapshotModel) -> WalletSnapshot:
    return WalletSnapshot(
        id=WalletSnapshotId(value=model.id),
        user_id=UserId(value=model.user_id),
        total_equity_usdt=float(model.total_equity_usdt),
        snapshot_date=model.snapshot_date,
        created_at=to_aware_utc(model.created_at),
    )


class WalletSnapshotPostgresRepository(IWalletSnapshotRepository):
    def __init__(self, session: AsyncSession):
        self.session = session

    async def save_daily_snapshot(
        self, user_id: UserId, total_equity_usdt: float, snapshot_date: date
    ) -> WalletSnapshot:
        result = await self.session.execute(
            select(WalletSnapshotModel).where(
                WalletSnapshotModel.user_id == user_id.value,
                WalletSnapshotModel.snapshot_date == snapshot_date,
            )
        )
        existing = result.scalar_one_or_none()
        if existing:
            # The day's snapshot tracks the latest sync, i.e. end-of-day equity.
            existing.total_equity_usdt = total_equity_usdt
            await self.session.flush()
            return _to_entity(existing)

        snapshot = WalletSnapshot(
            user_id=user_id,
            total_equity_usdt=total_equity_usdt,
            snapshot_date=snapshot_date,
            created_at=datetime.now(timezone.utc),
        )
        snapshot.validate()
        self.session.add(_to_model(snapshot))
        await self.session.flush()
        return snapshot

    async def find_by_id(self, entity_id: WalletSnapshotId) -> Optional[WalletSnapshot]:
        result = await self.session.execute(
            select(WalletSnapshotModel).where(WalletSnapshotModel.id == entity_id.value)
        )
        model = result.scalar_one_or_none()
        return _to_entity(model) if model else None
