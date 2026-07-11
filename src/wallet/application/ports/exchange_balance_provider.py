from abc import ABC, abstractmethod
from dataclasses import dataclass


@dataclass(frozen=True)
class AssetBalance:
    free: float
    locked: float


class IExchangeBalanceProvider(ABC):
    @abstractmethod
    async def fetch_balances(
        self, api_key: str, api_secret: str, is_testnet: bool
    ) -> dict[str, AssetBalance]:
        raise NotImplementedError()

    @abstractmethod
    async def estimate_total_equity_usdt(
        self,
        api_key: str,
        api_secret: str,
        is_testnet: bool,
        balances: dict[str, AssetBalance],
    ) -> float:
        raise NotImplementedError()
