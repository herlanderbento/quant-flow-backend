from fastapi import Depends
from sqlalchemy.ext.asyncio import AsyncSession

from account.domain.credential_repository import ICredentialRepository
from account.domain.user_repository import IUserRepository
from account.infra.api.credential.credential_dependencies import get_credential_repository
from account.infra.api.user.user_dependencies import get_user_repository
from shared.application.cryptography import IEncryption
from shared.infra.api.dependencies import get_encryption
from shared.infra.db.database import get_db_session
from wallet.application.ports.exchange_balance_provider import IExchangeBalanceProvider
from wallet.application.use_cases.wallet.get_wallets_by_user import GetWalletsByUserUseCase
from wallet.application.use_cases.wallet.sync_wallet import SyncWalletUseCase
from wallet.domain.repositories.wallet_repository import IWalletRepository
from wallet.domain.repositories.wallet_snapshot_repository import IWalletSnapshotRepository
from wallet.infra.db.wallet_postgres_repository import WalletPostgresRepository
from wallet.infra.db.wallet_snapshot_postgres_repository import WalletSnapshotPostgresRepository
from wallet.infra.gateway.bybit_exchange_balance_provider import BybitExchangeBalanceProvider


def get_wallet_repository(
    session: AsyncSession = Depends(get_db_session),
) -> IWalletRepository:
    return WalletPostgresRepository(session)


def get_wallet_snapshot_repository(
    session: AsyncSession = Depends(get_db_session),
) -> IWalletSnapshotRepository:
    return WalletSnapshotPostgresRepository(session)


def get_exchange_balance_provider() -> IExchangeBalanceProvider:
    return BybitExchangeBalanceProvider()


def get_sync_wallet_use_case(
    wallet_repo: IWalletRepository = Depends(get_wallet_repository),
    snapshot_repo: IWalletSnapshotRepository = Depends(get_wallet_snapshot_repository),
    credential_repo: ICredentialRepository = Depends(get_credential_repository),
    user_repo: IUserRepository = Depends(get_user_repository),
    encryption: IEncryption = Depends(get_encryption),
    balance_provider: IExchangeBalanceProvider = Depends(get_exchange_balance_provider),
) -> SyncWalletUseCase:
    return SyncWalletUseCase(
        wallet_repo,
        snapshot_repo,
        credential_repo,
        user_repo,
        encryption,
        balance_provider,
    )


def get_get_wallets_by_user_use_case(
    wallet_repo: IWalletRepository = Depends(get_wallet_repository),
    user_repo: IUserRepository = Depends(get_user_repository),
) -> GetWalletsByUserUseCase:
    return GetWalletsByUserUseCase(wallet_repo, user_repo)
