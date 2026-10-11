from datetime import date, datetime, timezone
from decimal import Decimal

from account.domain.user import UserId
from wallet.domain.wallet_snapshot import WalletSnapshot, WalletSnapshotId
from wallet.infra.db import wallet_snapshot_postgres_repository as repo


def test_snapshot_roundtrip_through_orm_model():
    snapshot = WalletSnapshot(
        user_id=UserId(), total_equity_usdt=123.45, snapshot_date=date(2026, 1, 1)
    )
    assert isinstance(snapshot.id, WalletSnapshotId)

    model = repo._to_model(snapshot)
    assert model.id == snapshot.id.value

    model.total_equity_usdt = Decimal("123.45000000")
    model.created_at = datetime.now(timezone.utc)
    restored = repo._to_entity(model)

    assert restored.id == snapshot.id
    assert restored.total_equity_usdt == 123.45
