from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from typing import Callable

from ml.data.ohlcv import TIMEFRAME_SECONDS, normalize_ohlcv
from ml.features.pipeline import WARMUP_CANDLES, FeatureError, latest_features
from ml.models.artifact import ArtifactError, ModelPredictor
from trader.domain.interface.strategy_interface import IBotStrategy, MarketData, TradeSignal

ML_STRATEGY_NAME = "ML_SIGNAL"


@dataclass(frozen=True)
class MLDecision:
    model_version: str | None
    feature_candle_close: datetime | None
    probability: float | None
    signal: TradeSignal
    reason: str | None  # why the model did not produce a usable signal
    features: dict | None = None


class MLSignalStrategy(IBotStrategy):
    """
    Turns a model probability into BUY / SELL / HOLD. Never more than a signal:
    every entry still goes through the bot cycle's risk guard, balance and minimum checks.
    """

    required_candles = WARMUP_CANDLES

    def __init__(
        self,
        predictor: ModelPredictor | None,
        timeframe: str = "1h",
        clock: Callable[[], datetime] | None = None,
        unavailable_reason: str | None = None,
    ):
        self.predictor = predictor
        self.timeframe = timeframe
        self.clock = clock
        self.unavailable_reason = unavailable_reason
        self.last_decision: MLDecision | None = None

    @property
    def name(self) -> str:
        return ML_STRATEGY_NAME

    async def analyze(self, market_data: MarketData) -> TradeSignal:
        self.last_decision = self.decide(market_data)
        return self.last_decision.signal

    def decide(self, market_data: MarketData) -> MLDecision:
        version = self.predictor.model_version if self.predictor else None
        if self.predictor is None:
            return MLDecision(None, None, None, TradeSignal.HOLD,
                              self.unavailable_reason or "model_unavailable")
        if not market_data.candles:
            return MLDecision(version, None, None, TradeSignal.HOLD, "no_candles")

        frame, _ = normalize_ohlcv(market_data.candles, self.timeframe)
        if frame.empty:
            return MLDecision(version, None, None, TradeSignal.HOLD, "no_valid_candles")
        period = timedelta(seconds=TIMEFRAME_SECONDS[self.timeframe])
        now = (
            self.clock() if self.clock
            else market_data.candle_closed_at
            or (frame["timestamp"].iloc[-1] + period).to_pydatetime()
        )
        try:
            vector = latest_features(frame, self.timeframe, now)
            probability = self.predictor.predict_proba(vector.values)
        except (FeatureError, ArtifactError) as error:
            return MLDecision(version, None, None, TradeSignal.HOLD, f"rejected: {error}")

        if probability >= self.predictor.buy_threshold:
            signal = TradeSignal.BUY
        elif probability <= self.predictor.sell_threshold:
            signal = TradeSignal.SELL
        else:
            signal = TradeSignal.HOLD
        return MLDecision(version, vector.candle_close_time, probability, signal, None,
                          vector.values)


def utc_now() -> datetime:
    return datetime.now(timezone.utc)
