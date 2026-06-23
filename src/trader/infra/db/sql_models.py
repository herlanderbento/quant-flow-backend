import uuid
from datetime import datetime, timezone
from typing import TYPE_CHECKING, List, Optional

from sqlalchemy import Boolean, DateTime, ForeignKey, Numeric, String
from sqlalchemy.dialects.postgresql import JSONB, UUID
from sqlalchemy.orm import Mapped, mapped_column, relationship

from shared.infra.db.database import Base

CASCADE_ALL_DELETE_ORPHAN = "all, delete-orphan"
FK_USERS_ID = "users.id"

if TYPE_CHECKING:
    from account.infra.db.sql_models import ExchangeCredentialModel, UserModel


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
    exchange_credential_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("exchange_credentials.id"), nullable=False
    )
    name: Mapped[str] = mapped_column(String(100), nullable=False)
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
    exchange_credential: Mapped["ExchangeCredentialModel"] = relationship(
        "ExchangeCredentialModel", back_populates="bots"
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


class TradeModel(Base):
    __tablename__ = "trades"

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
    price_executed: Mapped[float] = mapped_column(Numeric(18, 8), nullable=False)
    quantity: Mapped[float] = mapped_column(Numeric(18, 8), nullable=False)
    pnl_usd: Mapped[Optional[float]] = mapped_column(Numeric(18, 8), nullable=True)
    pnl_pct: Mapped[Optional[float]] = mapped_column(Numeric(8, 4), nullable=True)
    fee_paid: Mapped[Optional[float]] = mapped_column(Numeric(18, 8), nullable=True)
    binance_order_id: Mapped[Optional[str]] = mapped_column(String(100), nullable=True)
    executed_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=utcnow
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
    probability: Mapped[float] = mapped_column(Numeric(5, 4), nullable=False)
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
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=utcnow
    )

    # Relationships
    bot_config: Mapped["BotConfigModel"] = relationship(
        "BotConfigModel", back_populates="backtest_results"
    )