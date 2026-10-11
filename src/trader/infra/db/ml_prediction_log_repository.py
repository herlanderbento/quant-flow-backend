from dataclasses import dataclass
from datetime import datetime

from sqlalchemy.dialects.postgresql import insert
from sqlalchemy.ext.asyncio import AsyncSession

from trader.infra.db.sql_models import AIPredictionModel

SIGNAL_TO_PREDICTION = {"BUY": "BULLISH", "SELL": "BEARISH", "HOLD": "NEUTRAL"}


@dataclass(frozen=True)
class PredictionLogEntry:
    bot_id: object  # uuid.UUID
    symbol: str
    mode: str  # "shadow" | "active"
    model_version: str
    market_candle_close: datetime | None
    feature_candle_close: datetime | None
    probability: float | None
    decision: str
    strategy_signal: str | None
    reason: str | None
    buy_threshold: float | None
    sell_threshold: float | None
    features: dict | None


class MlPredictionLogRepository:
    def __init__(self, session: AsyncSession):
        self.session = session

    async def record(self, entry: PredictionLogEntry) -> bool:
        """Insert once per (bot, mode, market candle); returns False if already recorded."""
        statement = insert(AIPredictionModel).values(
            bot_config_id=entry.bot_id,
            symbol=entry.symbol,
            ai_model_version=entry.model_version[:50],
            features_payload=entry.features or {},
            prediction_signal=SIGNAL_TO_PREDICTION.get(entry.decision, "NEUTRAL"),
            probability=entry.probability,
            mode=entry.mode,
            market_candle_close=entry.market_candle_close,
            feature_candle_close=entry.feature_candle_close,
            decision=entry.decision,
            strategy_signal=entry.strategy_signal,
            reason=(entry.reason or None) and entry.reason[:300],
            buy_threshold=entry.buy_threshold,
            sell_threshold=entry.sell_threshold,
        ).on_conflict_do_nothing(constraint="uq_ai_predictions_bot_mode_candle")
        result = await self.session.execute(statement)
        return result.rowcount == 1
