import uuid
from datetime import datetime, date
from typing import TYPE_CHECKING
from sqlalchemy import String, Numeric, ForeignKey, DateTime, Date
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column, relationship

from shared.infra.db.database import Base

FK_USERS_ID = "users.id"

if TYPE_CHECKING:
    from account.infra.db.sql_models import UserModel


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
        DateTime,
        default=datetime.utcnow,
        onupdate=datetime.utcnow,
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
