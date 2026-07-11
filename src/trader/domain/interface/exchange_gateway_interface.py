from abc import ABC, abstractmethod
from dataclasses import dataclass
from typing import Optional

from trader.domain.interface.strategy_interface import MarketData

@dataclass
class OrderResult:
    order_id: str
    symbol: str
    side: str  # 'BUY' or 'SELL'
    price: float
    quantity: float
    status: str

class IExchangeGateway(ABC):
    @abstractmethod
    async def get_current_price(self, symbol: str) -> float:
        """Returns the current price of a trading pair (e.g. BTC/USDT)."""
        pass

    @abstractmethod
    async def get_market_snapshot(self, symbol: str, rsi_period: int = 14) -> MarketData:
        """Returns price and indicators for strategy analysis."""
        pass

    @abstractmethod
    async def get_balance(self, asset: str) -> float:  
        """Returns the available balance for a specific asset (e.g. USDT)."""
        pass

    @abstractmethod
    async def place_market_order(self, symbol: str, side: str, quantity: float) -> OrderResult:
        """Places a market buy or sell order."""
        pass

    @abstractmethod
    async def fetch_ohlcv_history(
        self,
        symbol: str,
        timeframe: str,
        since_ms: int,
        until_ms: int,
    ) -> list[list]:
        """Returns historical OHLCV candles for the given period."""
        pass

    @abstractmethod
    async def close(self) -> None:
        """Closes the async HTTP session."""
        pass