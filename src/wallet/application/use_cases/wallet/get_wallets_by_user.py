from dataclasses import dataclass

from account.domain.user import UserId
from account.domain.user_repository import IUserRepository
from shared.application.use_cases import UseCase
from shared.domain.exceptions import NotFoundException
from wallet.application.use_cases.wallet.common.wallet_output import WalletOutput
from wallet.domain.repositories.wallet_repository import IWalletRepository


@dataclass
class GetWalletsByUserInput:
    user_id: UserId

@dataclass(frozen=True)
class GetWalletsByUserOutput:
    items: list[WalletOutput]


class GetWalletsByUserUseCase(UseCase):
    def __init__(
        self,
        wallet_repository: IWalletRepository,
        user_repository: IUserRepository,
    ):
        self.wallet_repository = wallet_repository
        self.user_repository = user_repository

    async def execute(self, input: GetWalletsByUserInput) -> GetWalletsByUserOutput:
        if not await self.user_repository.find_by_id(input.user_id.value):
            raise NotFoundException(f"User with id {input.user_id} not found")

        wallets = await self.wallet_repository.find_by_user_id(input.user_id)
        return self.__to_output(wallets)

    def __to_output(self, wallets) -> GetWalletsByUserOutput:
        return GetWalletsByUserOutput(
            items=[WalletOutput.from_entity(wallet) for wallet in wallets]
        )
