"""trades: decision context recorded at entry

Revision ID: f1c2d3e4a5b6
Revises: e5a7b3c9d812
Create Date: 2026-10-10 16:00:00.000000

"""
from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision: str = "f1c2d3e4a5b6"
down_revision: Union[str, None] = "e5a7b3c9d812"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column(
        "trades", sa.Column("entry_context", postgresql.JSONB(), nullable=True)
    )


def downgrade() -> None:
    op.drop_column("trades", "entry_context")
