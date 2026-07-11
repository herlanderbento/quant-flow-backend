from abc import ABC, abstractmethod
from dataclasses import dataclass
from enum import Enum
from typing import Dict, Any

class TradeSignal(Enum):
    BUY = "BUY"
    SELL = "SELL"
    HOLD = "HOLD"

@dataclass
class MarketData:
    symbol: str
    current_price: float
    # In the future, candle data (Klines/OHLCV) or precomputed indicators can be passed here
    indicators: Dict[str, Any]

class IBotStrategy(ABC):
    """
    Base interface that all trading strategies must implement.
    """
    @property
    @abstractmethod
    def name(self) -> str:
        """Returns the unique strategy identifier (e.g. 'RSI_OVERSOLD')."""
        pass

    @abstractmethod
    async def analyze(self, market_data: MarketData) -> TradeSignal:
        """
        Receives the current market snapshot and returns the trading decision.
        """
        pass