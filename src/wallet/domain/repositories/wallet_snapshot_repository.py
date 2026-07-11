from abc import abstractmethod
from datetime import date

from account.domain.user import UserId
from wallet.domain.wallet_snapshot import WalletSnapshot, WalletSnapshotId


class IWalletSnapshotRepository:
    @abstractmethod
    def save_daily_snapshot(
        self, user_id: UserId, total_equity_usdt: float, snapshot_date: date
    ) -> WalletSnapshot:
        raise NotImplementedError()

    @abstractmethod
    def find_by_id(self, entity_id: WalletSnapshotId) -> WalletSnapshot | None:
        raise NotImplementedError()
