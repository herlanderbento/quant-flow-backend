"""exchange_credentials: encrypt api_key at rest, keep a display hint

Revision ID: c3d4e5f6a7b8
Revises: b2c3d4e5f6a7
Create Date: 2026-10-10 21:00:00.000000

Requires the same ENCRYPTION_KEY the application uses. Idempotent: values that are
already Fernet tokens are left alone.
"""
from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op
from cryptography.fernet import Fernet, InvalidToken

revision: str = "c3d4e5f6a7b8"
down_revision: Union[str, None] = "b2c3d4e5f6a7"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def _fernet() -> Fernet:
    from shared.infra.db.config import settings
    return Fernet(settings.ENCRYPTION_KEY.encode())


def _is_token(fernet: Fernet, value: str) -> bool:
    try:
        fernet.decrypt(value.encode())
        return True
    except (InvalidToken, ValueError):
        return False


def upgrade() -> None:
    op.alter_column("exchange_credentials", "api_key", existing_type=sa.String(255),
                    type_=sa.String(512), existing_nullable=False)
    op.add_column("exchange_credentials", sa.Column("api_key_hint", sa.String(8), nullable=True))

    connection = op.get_bind()
    rows = connection.execute(sa.text("SELECT id, api_key FROM exchange_credentials")).fetchall()
    if not rows:
        return
    fernet = _fernet()
    for credential_id, api_key in rows:
        if _is_token(fernet, api_key):
            continue
        connection.execute(
            sa.text("UPDATE exchange_credentials SET api_key = :key, api_key_hint = :hint WHERE id = :id"),
            {"key": fernet.encrypt(api_key.encode()).decode(), "hint": api_key[-4:], "id": credential_id},
        )


def downgrade() -> None:
    connection = op.get_bind()
    rows = connection.execute(sa.text("SELECT id, api_key FROM exchange_credentials")).fetchall()
    if rows:
        fernet = _fernet()
        for credential_id, api_key in rows:
            if _is_token(fernet, api_key):
                plain = fernet.decrypt(api_key.encode()).decode()
                connection.execute(sa.text("UPDATE exchange_credentials SET api_key = :key WHERE id = :id"),
                                   {"key": plain, "id": credential_id})
    op.drop_column("exchange_credentials", "api_key_hint")
    op.alter_column("exchange_credentials", "api_key", existing_type=sa.String(512),
                    type_=sa.String(255), existing_nullable=False)
