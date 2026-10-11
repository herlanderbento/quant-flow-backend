from dataclasses import dataclass
from datetime import date

from account.domain.credential import CredentialId
from account.domain.credential_repository import ICredentialRepository
from account.domain.user import UserId
from account.domain.user_repository import IUserRepository
from shared.application.cryptography import IEncryption
from shared.application.use_cases import UseCase
from shared.domain.exceptions import ConflictException, NotFoundException
from wallet.application.ports.exchange_balance_provider import IExchangeBalanceProvider
from wallet.application.use_cases.wallet.common.wallet_output import WalletOutput
from wallet.domain.repositories.wallet_repository import IWalletRepository
from wallet.domain.repositories.wallet_snapshot_repository import IWalletSnapshotRepository


@dataclass
class SyncWalletInput:
    user_id: UserId
    credential_id: CredentialId


@dataclass(frozen=True)
class SyncWalletOutput:
    wallets: list[WalletOutput]
    total_equity_usdt: float


class SyncWalletUseCase(UseCase):
    def __init__(
        self,
        wallet_repository: IWalletRepository,
        wallet_snapshot_repository: IWalletSnapshotRepository,
        credential_repository: ICredentialRepository,
        user_repository: IUserRepository,
        encryption: IEncryption,
        exchange_balance_provider: IExchangeBalanceProvider,
    ):
        self.wallet_repository = wallet_repository
        self.wallet_snapshot_repository = wallet_snapshot_repository
        self.credential_repository = credential_repository
        self.user_repository = user_repository
        self.encryption = encryption
        self.exchange_balance_provider = exchange_balance_provider

    async def execute(self, input: SyncWalletInput) -> SyncWalletOutput:
        if not await self.user_repository.find_by_id(input.user_id.value):
            raise NotFoundException(f"User with id {input.user_id.value} not found")

        credential = await self.credential_repository.find_by_id(input.credential_id.value)
        if not credential:
            raise NotFoundException(
                f"Credential with id {input.credential_id.value} not found"
            )

        if credential.user_id.value != input.user_id.value:
            raise ConflictException(
                "The provided credential does not belong to this user"
            )

        api_secret = self.encryption.decrypt(credential.api_secret)
        api_key = self.encryption.decrypt(credential.api_key)
        balances = await self.exchange_balance_provider.fetch_balances(
            api_key, api_secret, credential.is_testnet
        )

        wallets = []
        for asset, balance in balances.items():
            wallet = await self.wallet_repository.upsert_by_user_asset(
                user_id=input.user_id,
                asset=asset,
                free_balance=balance.free,
                locked_balance=balance.locked,
            )
            wallets.append(wallet)

        total_equity_usdt = (
            await self.exchange_balance_provider.estimate_total_equity_usdt(
                api_key,
                api_secret,
                credential.is_testnet,
                balances,
            )
        )

        await self.wallet_snapshot_repository.save_daily_snapshot(
            input.user_id, total_equity_usdt, date.today()
        )

        return self.__to_output(wallets, total_equity_usdt)

    def __to_output(
        self, wallets: list, total_equity_usdt: float
    ) -> SyncWalletOutput:
        return SyncWalletOutput(
            wallets=[WalletOutput.from_entity(wallet) for wallet in wallets],
            total_equity_usdt=total_equity_usdt,
        )
