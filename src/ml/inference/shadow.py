import logging
from datetime import datetime

from ml.inference.strategy import MLDecision, MLSignalStrategy
from trader.domain.interface.strategy_interface import IBotStrategy, MarketData, TradeSignal

logger = logging.getLogger(__name__)


class ShadowRecordingStrategy(IBotStrategy):
    """
    Wraps the bot's real strategy. The real strategy alone decides; the model's opinion
    on the same market data is only recorded. Model failures can never change the signal.
    """

    def __init__(self, inner: IBotStrategy, shadow: MLSignalStrategy):
        self.inner = inner
        self.shadow = shadow
        self.required_candles = max(
            int(getattr(inner, "required_candles", 0) or 0), shadow.required_candles
        )
        self.shadow_decision: MLDecision | None = None
        self.market_candle_close: datetime | None = None
        self.strategy_signal: TradeSignal | None = None

    @property
    def name(self) -> str:
        return self.inner.name

    async def analyze(self, market_data: MarketData) -> TradeSignal:
        signal = await self.inner.analyze(market_data)
        try:
            self.shadow_decision = self.shadow.decide(market_data)
            self.market_candle_close = market_data.candle_closed_at
            self.strategy_signal = signal
        except Exception:
            logger.exception("Shadow model evaluation failed; strategy signal unaffected")
        return signal
