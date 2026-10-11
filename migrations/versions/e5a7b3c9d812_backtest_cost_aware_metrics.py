"""backtest: cost-aware metrics and the costs used to produce them

Revision ID: e5a7b3c9d812
Revises: d3e9f0a1b204
Create Date: 2026-10-10 14:00:00.000000

"""
from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

revision: str = "e5a7b3c9d812"
down_revision: Union[str, None] = "d3e9f0a1b204"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None

COLUMNS = (
    ("timeframe", sa.String(10)),
    ("profit_factor", sa.Numeric(12, 4)),
    ("expectancy_pct", sa.Numeric(12, 4)),
    ("buy_and_hold_return_pct", sa.Numeric(12, 4)),
    ("exposure_pct", sa.Numeric(8, 4)),
    ("fees_paid", sa.Numeric(18, 8)),
    ("taker_fee_rate", sa.Numeric(8, 6)),
    ("slippage_bps", sa.Numeric(8, 2)),
)


def upgrade() -> None:
    for name, type_ in COLUMNS:
        op.add_column("backtest_results", sa.Column(name, type_, nullable=True))


def downgrade() -> None:
    for name, _ in reversed(COLUMNS):
        op.drop_column("backtest_results", name)
