"""worker_status: heartbeat and counters per worker process

Revision ID: a7b8c9d0e1f2
Revises: f1c2d3e4a5b6
Create Date: 2026-10-10 18:00:00.000000

"""
from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision: str = "a7b8c9d0e1f2"
down_revision: Union[str, None] = "f1c2d3e4a5b6"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        "worker_status",
        sa.Column("worker_id", sa.String(64), primary_key=True),
        sa.Column("trading_mode", sa.String(10), nullable=False),
        sa.Column("hostname", sa.String(255), nullable=False),
        sa.Column("started_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("last_heartbeat_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("last_cycle_started_at", sa.DateTime(timezone=True)),
        sa.Column("last_cycle_finished_at", sa.DateTime(timezone=True)),
        sa.Column("last_market_data_at", sa.DateTime(timezone=True)),
        sa.Column("cycles_total", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("cycle_errors_total", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("consecutive_failures", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("max_cycle_gap_seconds", sa.Numeric(12, 3), nullable=False, server_default="0"),
        sa.Column("bots_last_cycle", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("outcome_counts", postgresql.JSONB(), nullable=False,
                  server_default=sa.text("'{}'::jsonb")),
        sa.Column("last_error", sa.String(500)),
        sa.Column("last_audit_at", sa.DateTime(timezone=True)),
        sa.Column("audit_issues", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("audit_details", postgresql.JSONB()),
        sa.Column("stopped_at", sa.DateTime(timezone=True)),
    )
    op.create_index("ix_worker_status_last_heartbeat_at", "worker_status", ["last_heartbeat_at"])


def downgrade() -> None:
    op.drop_index("ix_worker_status_last_heartbeat_at", table_name="worker_status")
    op.drop_table("worker_status")
