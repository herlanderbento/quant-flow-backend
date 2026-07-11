from datetime import datetime
from uuid import UUID

from pydantic import BaseModel, ConfigDict

from wallet.application.use_cases.wallet.common.wallet_output import WalletOutput
from wallet.application.use_cases.wallet.get_wallets_by_user import GetWalletsByUserOutput
from wallet.application.use_cases.wallet.sync_wallet import SyncWalletOutput


class WalletPresenter(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: UUID
    user_id: UUID
    asset: str
    free_balance: float
    locked_balance: float
    updated_at: datetime

    @classmethod
    def from_output(cls, output: WalletOutput) -> "WalletPresenter":
        return cls(
            id=output.id,
            user_id=output.user_id,
            asset=output.asset,
            free_balance=output.free_balance,
            locked_balance=output.locked_balance,
            updated_at=output.updated_at,
        )


class WalletCollectionPresenter(BaseModel):
    data: list[WalletPresenter]

    @classmethod
    def from_get_output(cls, output: GetWalletsByUserOutput) -> "WalletCollectionPresenter":
        return cls(
            data=[WalletPresenter.from_output(item) for item in output.items]
        )


class SyncWalletPresenter(BaseModel):
    wallets: list[WalletPresenter]
    total_equity_usdt: float

    @classmethod
    def from_output(cls, output: SyncWalletOutput) -> "SyncWalletPresenter":
        return cls(
            wallets=[WalletPresenter.from_output(wallet) for wallet in output.wallets],
            total_equity_usdt=output.total_equity_usdt,
        )
