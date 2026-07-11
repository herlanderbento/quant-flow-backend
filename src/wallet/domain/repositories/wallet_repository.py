from abc import abstractmethod

from account.domain.user import UserId
from shared.domain.repository_interface import IRepository
from wallet.domain.wallet import Wallet, WalletId


class IWalletRepository(IRepository[Wallet, WalletId]):
    @abstractmethod
    def find_by_user_id(self, user_id: UserId) -> list[Wallet]:
        raise NotImplementedError()

    @abstractmethod
    def upsert_by_user_asset(
        self,
        user_id: UserId,
        asset: str,
        free_balance: float,
        locked_balance: float,
    ) -> Wallet:
        raise NotImplementedError()
