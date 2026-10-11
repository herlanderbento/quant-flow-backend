"""trade order lifecycle: client order ids, exit tracking, one active trade per bot

Revision ID: d3e9f0a1b204
Revises: c7d1a4e8b502
Create Date: 2026-10-10 12:00:00.000000

"""
from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

revision: str = "d3e9f0a1b204"
down_revision: Union[str, None] = "c7d1a4e8b502"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None

ACTIVE_STATUSES = "status IN ('PENDING_OPEN', 'OPEN', 'PENDING_CLOSE')"


def upgrade() -> None:
    op.add_column("trades", sa.Column("client_order_id", sa.String(64), nullable=True))
    op.add_column("trades", sa.Column("open_quantity", sa.Numeric(18, 8), nullable=True))
    op.add_column("trades", sa.Column("entry_cost", sa.Numeric(18, 8), nullable=True))
    op.add_column("trades", sa.Column("exit_client_order_id", sa.String(64), nullable=True))
    op.add_column("trades", sa.Column("exit_order_id", sa.String(100), nullable=True))
    op.add_column("trades", sa.Column("exit_price", sa.Numeric(18, 8), nullable=True))
    op.add_column("trades", sa.Column("exit_reason", sa.String(30), nullable=True))
    op.add_column(
        "trades",
        sa.Column(
            "updated_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.func.now(),
        ),
    )
    op.alter_column("trades", "price_executed", existing_type=sa.Numeric(18, 8), nullable=True)

    # Legacy open trades keep being managed: derive the fields the new lifecycle needs.
    op.execute(
        "UPDATE trades SET open_quantity = quantity, "
        "entry_cost = price_executed * quantity "
        "WHERE status = 'OPEN' AND open_quantity IS NULL"
    )

    op.create_unique_constraint("uq_trades_client_order_id", "trades", ["client_order_id"])
    op.create_unique_constraint(
        "uq_trades_exit_client_order_id", "trades", ["exit_client_order_id"]
    )
    # Fails loudly if a bot already has several open trades: resolve those by hand first.
    op.create_index(
        "uq_trades_one_active_per_bot",
        "trades",
        ["bot_config_id"],
        unique=True,
        postgresql_where=sa.text(ACTIVE_STATUSES),
    )


def downgrade() -> None:
    op.drop_index("uq_trades_one_active_per_bot", table_name="trades")
    op.drop_constraint("uq_trades_exit_client_order_id", "trades", type_="unique")
    op.drop_constraint("uq_trades_client_order_id", "trades", type_="unique")
    op.execute("UPDATE trades SET price_executed = 0 WHERE price_executed IS NULL")
    op.alter_column("trades", "price_executed", existing_type=sa.Numeric(18, 8), nullable=False)
    for column in (
        "updated_at",
        "exit_reason",
        "exit_price",
        "exit_order_id",
        "exit_client_order_id",
        "entry_cost",
        "open_quantity",
        "client_order_id",
    ):
        op.drop_column("trades", column)
