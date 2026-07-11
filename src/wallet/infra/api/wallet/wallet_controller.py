from uuid import UUID

from fastapi import APIRouter, Depends, status
from pydantic import BaseModel

from account.domain.credential import CredentialId
from account.domain.user import UserId
from shared.infra.api.auth_dependencies import AuthContext, require_authenticated
from wallet.application.use_cases.wallet.get_wallets_by_user import (
    GetWalletsByUserInput,
    GetWalletsByUserUseCase,
)
from wallet.application.use_cases.wallet.sync_wallet import SyncWalletInput, SyncWalletUseCase
from wallet.infra.api.wallet.wallet_dependencies import (
    get_get_wallets_by_user_use_case,
    get_sync_wallet_use_case,
)
from wallet.infra.api.wallet.wallet_presenter import (
    SyncWalletPresenter,
    WalletCollectionPresenter,
)

router = APIRouter(prefix="/wallets", tags=["Wallets"])


class SyncWalletRequest(BaseModel):
    credential_id: UUID


@router.get("", response_model=WalletCollectionPresenter, status_code=status.HTTP_200_OK)
async def get_wallets(
    _auth: AuthContext = Depends(require_authenticated),
    use_case: GetWalletsByUserUseCase = Depends(get_get_wallets_by_user_use_case),
):
    output = await use_case.execute(GetWalletsByUserInput(user_id=UserId(value=_auth.user_id)))
    return WalletCollectionPresenter.from_get_output(output)


@router.post("/sync", response_model=SyncWalletPresenter, status_code=status.HTTP_200_OK)
async def sync_wallets(
    request: SyncWalletRequest,
    _auth: AuthContext = Depends(require_authenticated),
    use_case: SyncWalletUseCase = Depends(get_sync_wallet_use_case),
):
    output = await use_case.execute(
        SyncWalletInput(
            user_id=UserId(value=_auth.user_id),
            credential_id=CredentialId(value=request.credential_id),
        )
    )
    return SyncWalletPresenter.from_output(output)
