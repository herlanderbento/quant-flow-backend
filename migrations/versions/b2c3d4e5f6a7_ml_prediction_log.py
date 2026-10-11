"""ai_predictions: shadow/active prediction log for the ML strategy

Revision ID: b2c3d4e5f6a7
Revises: a7b8c9d0e1f2
Create Date: 2026-10-10 20:00:00.000000

"""
from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

revision: str = "b2c3d4e5f6a7"
down_revision: Union[str, None] = "a7b8c9d0e1f2"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.alter_column("ai_predictions", "probability", existing_type=sa.Numeric(5, 4),
                    type_=sa.Numeric(7, 6), nullable=True)
    op.add_column("ai_predictions", sa.Column("mode", sa.String(10), nullable=False,
                                              server_default="shadow"))
    op.add_column("ai_predictions", sa.Column("market_candle_close", sa.DateTime(timezone=True)))
    op.add_column("ai_predictions", sa.Column("feature_candle_close", sa.DateTime(timezone=True)))
    op.add_column("ai_predictions", sa.Column("decision", sa.String(10)))
    op.add_column("ai_predictions", sa.Column("strategy_signal", sa.String(10)))
    op.add_column("ai_predictions", sa.Column("reason", sa.String(300)))
    op.add_column("ai_predictions", sa.Column("buy_threshold", sa.Numeric(7, 6)))
    op.add_column("ai_predictions", sa.Column("sell_threshold", sa.Numeric(7, 6)))
    op.create_unique_constraint("uq_ai_predictions_bot_mode_candle", "ai_predictions",
                                ["bot_config_id", "mode", "market_candle_close"])


def downgrade() -> None:
    op.drop_constraint("uq_ai_predictions_bot_mode_candle", "ai_predictions", type_="unique")
    for column in ("sell_threshold", "buy_threshold", "reason", "strategy_signal", "decision",
                   "feature_candle_close", "market_candle_close", "mode"):
        op.drop_column("ai_predictions", column)
    op.execute("DELETE FROM ai_predictions WHERE probability IS NULL")
    op.alter_column("ai_predictions", "probability", existing_type=sa.Numeric(7, 6),
                    type_=sa.Numeric(5, 4), nullable=False)
