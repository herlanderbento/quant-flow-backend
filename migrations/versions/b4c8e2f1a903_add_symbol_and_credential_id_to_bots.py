"""add symbol and rename credential_id on bot_configs

Revision ID: b4c8e2f1a903
Revises: efa1a59d23c3
Create Date: 2026-06-23 16:35:00.000000

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa

revision: str = "b4c8e2f1a903"
down_revision: Union[str, None] = "efa1a59d23c3"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column(
        "bot_configs",
        sa.Column(
            "symbol",
            sa.String(length=20),
            nullable=False,
            server_default="BTC/USDT",
        ),
    )
    op.alter_column("bot_configs", "symbol", server_default=None)

    op.alter_column(
        "bot_configs",
        "exchange_credential_id",
        new_column_name="credential_id",
    )


def downgrade() -> None:
    op.alter_column(
        "bot_configs",
        "credential_id",
        new_column_name="exchange_credential_id",
    )
    op.drop_column("bot_configs", "symbol")
