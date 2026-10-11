from abc import ABC, abstractmethod
from dataclasses import dataclass
from datetime import datetime
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
    indicators: Dict[str, Any]
    # Close time of the last *closed* candle the indicators were computed from.
    candle_closed_at: datetime | None = None
    # Closed candles [open_time_ms, open, high, low, close, volume], oldest first,
    # for strategies that compute their own features (e.g. the ML strategy).
    candles: list[list[float]] | None = None

# Timeframe the live worker trades on; backtests on other timeframes do not reflect live behaviour.
LIVE_TIMEFRAME = "1h"
# Closed candles delivered to strategies (>= the ML feature warm-up).
SNAPSHOT_CANDLES = 200

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