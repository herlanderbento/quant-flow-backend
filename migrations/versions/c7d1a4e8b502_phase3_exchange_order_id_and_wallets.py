"""phase 3: exchange_order_id rename and wallets unique constraint

Revision ID: c7d1a4e8b502
Revises: b4c8e2f1a903
Create Date: 2026-06-23 20:05:00.000000

"""
from typing import Sequence, Union

from alembic import op

revision: str = "c7d1a4e8b502"
down_revision: Union[str, None] = "b4c8e2f1a903"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.alter_column(
        "trades",
        "binance_order_id",
        new_column_name="exchange_order_id",
    )
    op.create_unique_constraint(
        "uq_wallets_user_asset", "wallets", ["user_id", "asset"]
    )


def downgrade() -> None:
    op.drop_constraint("uq_wallets_user_asset", "wallets", type_="unique")
    op.alter_column(
        "trades",
        "exchange_order_id",
        new_column_name="binance_order_id",
    )
