import uuid
from datetime import datetime, date
from typing import List, Optional
from sqlalchemy import String, Boolean, Numeric, ForeignKey, DateTime, Date
from sqlalchemy.dialects.postgresql import JSONB, UUID
from sqlalchemy.orm import Mapped, mapped_column, relationship

from shared.infra.db.database import Base

CASCADE_ALL_DELETE_ORPHAN = "all, delete-orphan"
FK_USERS_ID = "users.id"


# ==========================================
# MODULE: AUTH / USERS
# ==========================================
class UserModel(Base):
    __tablename__ = "users"

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, default=uuid.uuid4
    )
    name: Mapped[str] = mapped_column(String(100), nullable=False)
    email: Mapped[str] = mapped_column(String(150), unique=True, nullable=False)
    password: Mapped[str] = mapped_column(String(255), nullable=False)
    is_active: Mapped[bool] = mapped_column(Boolean, default=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)
    updated_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)

    # Relationships
    api_keys: Mapped[List["UserApiKeyModel"]] = relationship(
        "UserApiKeyModel", back_populates="user", cascade=CASCADE_ALL_DELETE_ORPHAN
    )
    wallets: Mapped[List["WalletModel"]] = relationship(
        "WalletModel", back_populates="user", cascade=CASCADE_ALL_DELETE_ORPHAN
    )
    bots: Mapped[List["BotConfigModel"]] = relationship(
        "BotConfigModel", back_populates="user"
    )


class UserApiKeyModel(Base):
    __tablename__ = "user_api_keys"

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, default=uuid.uuid4
    )
    user_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey(FK_USERS_ID, ondelete="CASCADE"), nullable=False
    )
    exchange_name: Mapped[str] = mapped_column(String(50), default="BINANCE")
    api_key: Mapped[str] = mapped_column(String(255), nullable=False)
    api_secret_encrypted: Mapped[str] = mapped_column(String(512), nullable=False)
    is_testnet: Mapped[bool] = mapped_column(Boolean, default=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)

    user: Mapped["UserModel"] = relationship("UserModel", back_populates="api_keys")
    bots: Mapped[List["BotConfigModel"]] = relationship(
        "BotConfigModel", back_populates="api_key"
    )


# ==========================================
# MODULE: WALLET
# ==========================================
class WalletModel(Base):
    __tablename__ = "wallets"

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, default=uuid.uuid4
    )
    user_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey(FK_USERS_ID, ondelete="CASCADE"), nullable=False
    )
    asset: Mapped[str] = mapped_column(String(20), nullable=False)  # 'USDT', 'BTC'
    free_balance: Mapped[float] = mapped_column(Numeric(18, 8), default=0.0)
    locked_balance: Mapped[float] = mapped_column(Numeric(18, 8), default=0.0)
    updated_at: Mapped[datetime] = mapped_column(
        DateTime, default=datetime.utcnow, onupdate=datetime.utcnow
    )

    user: Mapped["UserModel"] = relationship("UserModel", back_populates="wallets")


class WalletSnapshotModel(Base):
    __tablename__ = "wallet_snapshots"

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, default=uuid.uuid4
    )
    user_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey(FK_USERS_ID, ondelete="CASCADE"), nullable=False
    )
    total_equity_usdt: Mapped[float] = mapped_column(Numeric(18, 8), nullable=False)
    snapshot_date: Mapped[date] = mapped_column(Date, default=date.today)


# ==========================================
# MODULE: TRADER / BOTS / AI
# ==========================================
class BotConfigModel(Base):
    __tablename__ = "bot_configs"

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, default=uuid.uuid4
    )
    user_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey(FK_USERS_ID), nullable=False
    )
    api_key_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("user_api_keys.id"), nullable=False
    )
    name: Mapped[str] = mapped_column(String(100), nullable=False)
    strategy_type: Mapped[str] = mapped_column(
        String(50), nullable=False
    )  # 'SCALPER_LSTM', 'SMA_RSI'
    is_active: Mapped[bool] = mapped_column(Boolean, default=False)
    allocated_capital: Mapped[float] = mapped_column(Numeric(18, 8), nullable=False)
    stop_loss_pct: Mapped[float] = mapped_column(Numeric(5, 2), nullable=False)
    take_profit_pct: Mapped[float] = mapped_column(Numeric(5, 2), nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)

    user: Mapped["UserModel"] = relationship("UserModel", back_populates="bots")
    api_key: Mapped["UserApiKeyModel"] = relationship(
        "UserApiKeyModel", back_populates="bots"
    )
    trades: Mapped[List["TradeModel"]] = relationship(
        "TradeModel", back_populates="bot_config", cascade=CASCADE_ALL_DELETE_ORPHAN
    )


class TradeModel(Base):
    __tablename__ = "trades"

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, default=uuid.uuid4
    )
    bot_config_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("bot_configs.id"), nullable=False
    )
    symbol: Mapped[str] = mapped_column(String(20), nullable=False)
    side: Mapped[str] = mapped_column(String(10), nullable=False)  # 'BUY', 'SELL'
    price_executed: Mapped[float] = mapped_column(Numeric(18, 8), nullable=False)
    quantity: Mapped[float] = mapped_column(Numeric(18, 8), nullable=False)
    binance_order_id: Mapped[Optional[str]] = mapped_column(String(100), nullable=True)
    executed_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)

    bot_config: Mapped["BotConfigModel"] = relationship(
        "BotConfigModel", back_populates="trades"
    )


class AIPredictionModel(Base):
    __tablename__ = "ai_predictions"

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, default=uuid.uuid4
    )
    symbol: Mapped[str] = mapped_column(String(20), nullable=False)
    ai_model_version: Mapped[str] = mapped_column(String(50), nullable=False)
    features_payload: Mapped[dict] = mapped_column(
        JSONB, nullable=False
    )  # RSI, MACD, SMA
    prediction_signal: Mapped[str] = mapped_column(
        String(20), nullable=False
    )  # 'BULLISH', 'BEARISH'
    probability: Mapped[float] = mapped_column(Numeric(5, 4), nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)
