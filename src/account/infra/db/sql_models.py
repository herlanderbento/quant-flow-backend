import uuid
from datetime import datetime
from typing import TYPE_CHECKING, List
from sqlalchemy import String, Boolean, ForeignKey, DateTime
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column, relationship

from shared.infra.db.database import Base

if TYPE_CHECKING:
    from trader.infra.db.sql_models import BotConfigModel
    from wallet.infra.db.sql_models import WalletModel

CASCADE_ALL_DELETE_ORPHAN = "all, delete-orphan"
FK_USERS_ID = "users.id"
FK_EXCHANGE_CREDENTIALS_ID = "exchange_credentials.id"


class UserModel(Base):
    __tablename__ = "users"

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, default=uuid.uuid4
    )
    name: Mapped[str] = mapped_column(String(100), nullable=False)
    email: Mapped[str] = mapped_column(String(150), unique=True, nullable=False)
    password: Mapped[str] = mapped_column(String(255), nullable=False)
    is_active: Mapped[bool] = mapped_column(Boolean, default=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime, default=datetime.utcnow
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime,
        default=datetime.utcnow,
        onupdate=datetime.utcnow,
    )

    # Relationships
    exchange_credentials: Mapped[List["ExchangeCredentialModel"]] = relationship(
        "ExchangeCredentialModel",
        back_populates="user",
        cascade=CASCADE_ALL_DELETE_ORPHAN,
    )
    wallets: Mapped[List["WalletModel"]] = relationship(
        "WalletModel", back_populates="user", cascade=CASCADE_ALL_DELETE_ORPHAN
    )
    bots: Mapped[List["BotConfigModel"]] = relationship(
        "BotConfigModel", back_populates="user"
    )


class ExchangeCredentialModel(Base):
    __tablename__ = "exchange_credentials"

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

    user: Mapped["UserModel"] = relationship(
        "UserModel", back_populates="exchange_credentials"
    )
    bots: Mapped[List["BotConfigModel"]] = relationship(
        "BotConfigModel", back_populates="exchange_credential"
    )
