import uuid
from datetime import datetime, timezone
from typing import TYPE_CHECKING, List, Optional

from sqlalchemy import Boolean, DateTime, ForeignKey, Index, Numeric, String, UniqueConstraint, text
from sqlalchemy.dialects.postgresql import JSONB, UUID
from sqlalchemy.orm import Mapped, mapped_column, relationship

from shared.infra.db.database import Base

CASCADE_ALL_DELETE_ORPHAN = "all, delete-orphan"
FK_USERS_ID = "users.id"

if TYPE_CHECKING:
    from account.infra.db.sql_models import CredentialModel, UserModel


def utcnow() -> datetime:
    return datetime.now(timezone.utc)


class BotConfigModel(Base):
    __tablename__ = "bot_configs"

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, default=uuid.uuid4
    )
    user_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey(FK_USERS_ID), nullable=False
    )
    credential_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("exchange_credentials.id"), nullable=False
    )
    name: Mapped[str] = mapped_column(String(100), nullable=False)
    symbol: Mapped[str] = mapped_column(String(20), nullable=False)
    strategy_type: Mapped[str] = mapped_column(
        String(50), nullable=False
    )  # 'SCALPER_LSTM', 'SMA_RSI'
    is_active: Mapped[bool] = mapped_column(Boolean, default=False)
    allocated_capital: Mapped[float] = mapped_column(Numeric(18, 8), nullable=False)
    stop_loss_pct: Mapped[float] = mapped_column(Numeric(5, 2), nullable=False)
    take_profit_pct: Mapped[float] = mapped_column(Numeric(5, 2), nullable=False)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=utcnow
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=utcnow, onupdate=utcnow
    )

    # Relationships
    user: Mapped["UserModel"] = relationship("UserModel", back_populates="bots")
    credential: Mapped["CredentialModel"] = relationship(
        "CredentialModel", back_populates="bots"
    )
    trades: Mapped[List["TradeModel"]] = relationship(
        "TradeModel", back_populates="bot_config", cascade=CASCADE_ALL_DELETE_ORPHAN
    )
    ai_predictions: Mapped[List["AIPredictionModel"]] = relationship(
        "AIPredictionModel", back_populates="bot_config", cascade=CASCADE_ALL_DELETE_ORPHAN
    )
    backtest_results: Mapped[List["BacktestResultModel"]] = relationship(
        "BacktestResultModel", back_populates="bot_config", cascade=CASCADE_ALL_DELETE_ORPHAN
    )


ACTIVE_TRADE_STATUSES_SQL = "status IN ('PENDING_OPEN', 'OPEN', 'PENDING_CLOSE')"


class TradeModel(Base):
    __tablename__ = "trades"
    __table_args__ = (
        # At most one non-final trade per bot: the database-level guard against
        # duplicate entries, including from concurrent workers.
        Index(
            "uq_trades_one_active_per_bot",
            "bot_config_id",
            unique=True,
            postgresql_where=text(ACTIVE_TRADE_STATUSES_SQL),
        ),
    )

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, default=uuid.uuid4
    )
    bot_config_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("bot_configs.id"), nullable=False
    )
    ai_prediction_id: Mapped[Optional[uuid.UUID]] = mapped_column(
        UUID(as_uuid=True), ForeignKey("ai_predictions.id"), nullable=True
    )
    symbol: Mapped[str] = mapped_column(String(20), nullable=False)
    side: Mapped[str] = mapped_column(String(10), nullable=False)  # 'BUY', 'SELL'
    status: Mapped[str] = mapped_column(
        String(20), nullable=False, default="OPEN"
    )  # 'OPEN', 'CLOSED', 'CANCELLED'
    client_order_id: Mapped[Optional[str]] = mapped_column(
        String(64), nullable=True, unique=True
    )
    entry_context: Mapped[Optional[dict]] = mapped_column(
        JSONB(none_as_null=True), nullable=True
    )
    price_executed: Mapped[Optional[float]] = mapped_column(Numeric(18, 8), nullable=True)
    quantity: Mapped[float] = mapped_column(Numeric(18, 8), nullable=False)
    open_quantity: Mapped[Optional[float]] = mapped_column(Numeric(18, 8), nullable=True)
    entry_cost: Mapped[Optional[float]] = mapped_column(Numeric(18, 8), nullable=True)
    pnl_usd: Mapped[Optional[float]] = mapped_column(Numeric(18, 8), nullable=True)
    pnl_pct: Mapped[Optional[float]] = mapped_column(Numeric(8, 4), nullable=True)
    fee_paid: Mapped[Optional[float]] = mapped_column(Numeric(18, 8), nullable=True)
    exchange_order_id: Mapped[Optional[str]] = mapped_column(String(100), nullable=True)
    exit_client_order_id: Mapped[Optional[str]] = mapped_column(
        String(64), nullable=True, unique=True
    )
    exit_order_id: Mapped[Optional[str]] = mapped_column(String(100), nullable=True)
    exit_price: Mapped[Optional[float]] = mapped_column(Numeric(18, 8), nullable=True)
    exit_reason: Mapped[Optional[str]] = mapped_column(String(30), nullable=True)
    executed_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=utcnow
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=utcnow, onupdate=utcnow
    )
    closed_at: Mapped[Optional[datetime]] = mapped_column(
        DateTime(timezone=True), nullable=True
    )

    # Relationships
    bot_config: Mapped["BotConfigModel"] = relationship(
        "BotConfigModel", back_populates="trades"
    )
    ai_prediction: Mapped[Optional["AIPredictionModel"]] = relationship(
        "AIPredictionModel", back_populates="trades"
    )


class AIPredictionModel(Base):
    __tablename__ = "ai_predictions"
    __table_args__ = (
        UniqueConstraint(
            "bot_config_id", "mode", "market_candle_close",
            name="uq_ai_predictions_bot_mode_candle",
        ),
    )

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, default=uuid.uuid4
    )
    bot_config_id: Mapped[Optional[uuid.UUID]] = mapped_column(
        UUID(as_uuid=True), ForeignKey("bot_configs.id"), nullable=True
    )
    symbol: Mapped[str] = mapped_column(String(20), nullable=False)
    ai_model_version: Mapped[str] = mapped_column(String(50), nullable=False)
    features_payload: Mapped[dict] = mapped_column(JSONB, nullable=False)
    prediction_signal: Mapped[str] = mapped_column(
        String(20), nullable=False
    )  # 'BULLISH', 'BEARISH', 'NEUTRAL'
    # Null when the model could not produce a prediction (see `reason`).
    probability: Mapped[Optional[float]] = mapped_column(Numeric(7, 6), nullable=True)
    # 'shadow': logged only, never used. 'active': drove an ML_SIGNAL bot's decision.
    mode: Mapped[str] = mapped_column(String(10), nullable=False, default="shadow")
    market_candle_close: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True))
    feature_candle_close: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True))
    decision: Mapped[Optional[str]] = mapped_column(String(10))  # model's BUY / SELL / HOLD
    strategy_signal: Mapped[Optional[str]] = mapped_column(String(10))  # signal actually used
    reason: Mapped[Optional[str]] = mapped_column(String(300))
    buy_threshold: Mapped[Optional[float]] = mapped_column(Numeric(7, 6))
    sell_threshold: Mapped[Optional[float]] = mapped_column(Numeric(7, 6))
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=utcnow
    )

    # Relationships
    bot_config: Mapped[Optional["BotConfigModel"]] = relationship(
        "BotConfigModel", back_populates="ai_predictions"
    )
    trades: Mapped[List["TradeModel"]] = relationship(
        "TradeModel", back_populates="ai_prediction"
    )


class BacktestResultModel(Base):
    __tablename__ = "backtest_results"

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, default=uuid.uuid4
    )
    bot_config_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("bot_configs.id"), nullable=False
    )
    strategy_type: Mapped[str] = mapped_column(String(50), nullable=False)
    symbol: Mapped[str] = mapped_column(String(20), nullable=False)
    period_start: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    period_end: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    total_return_pct: Mapped[Optional[float]] = mapped_column(Numeric(8, 4), nullable=True)
    sharpe_ratio: Mapped[Optional[float]] = mapped_column(Numeric(8, 4), nullable=True)
    max_drawdown_pct: Mapped[Optional[float]] = mapped_column(Numeric(8, 4), nullable=True)
    win_rate: Mapped[Optional[float]] = mapped_column(Numeric(8, 4), nullable=True)
    total_trades: Mapped[Optional[int]] = mapped_column(nullable=True)
    timeframe: Mapped[Optional[str]] = mapped_column(String(10), nullable=True)
    profit_factor: Mapped[Optional[float]] = mapped_column(Numeric(12, 4), nullable=True)
    expectancy_pct: Mapped[Optional[float]] = mapped_column(Numeric(12, 4), nullable=True)
    buy_and_hold_return_pct: Mapped[Optional[float]] = mapped_column(Numeric(12, 4), nullable=True)
    exposure_pct: Mapped[Optional[float]] = mapped_column(Numeric(8, 4), nullable=True)
    fees_paid: Mapped[Optional[float]] = mapped_column(Numeric(18, 8), nullable=True)
    taker_fee_rate: Mapped[Optional[float]] = mapped_column(Numeric(8, 6), nullable=True)
    slippage_bps: Mapped[Optional[float]] = mapped_column(Numeric(8, 2), nullable=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=utcnow
    )

    # Relationships
    bot_config: Mapped["BotConfigModel"] = relationship(
        "BotConfigModel", back_populates="backtest_results"
    )

class WorkerStatusModel(Base):
    """Heartbeat and counters of one worker process (one row per process)."""

    __tablename__ = "worker_status"

    worker_id: Mapped[str] = mapped_column(String(64), primary_key=True)
    trading_mode: Mapped[str] = mapped_column(String(10), nullable=False)
    hostname: Mapped[str] = mapped_column(String(255), nullable=False)
    started_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    last_heartbeat_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    last_cycle_started_at: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True))
    last_cycle_finished_at: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True))
    last_market_data_at: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True))
    cycles_total: Mapped[int] = mapped_column(nullable=False, default=0)
    cycle_errors_total: Mapped[int] = mapped_column(nullable=False, default=0)
    consecutive_failures: Mapped[int] = mapped_column(nullable=False, default=0)
    max_cycle_gap_seconds: Mapped[float] = mapped_column(Numeric(12, 3), nullable=False, default=0)
    bots_last_cycle: Mapped[int] = mapped_column(nullable=False, default=0)
    outcome_counts: Mapped[dict] = mapped_column(JSONB, nullable=False, default=dict)
    last_error: Mapped[Optional[str]] = mapped_column(String(500))
    last_audit_at: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True))
    audit_issues: Mapped[int] = mapped_column(nullable=False, default=0)
    audit_details: Mapped[Optional[dict]] = mapped_column(JSONB(none_as_null=True))
    stopped_at: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True))
