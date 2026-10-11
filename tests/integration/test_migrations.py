import uuid
from datetime import datetime, timezone

import psycopg2

from tests.integration.conftest import run_alembic, sync_url

LEGACY_REVISION = "c7d1a4e8b502"  # schema before the order lifecycle work


def _query(database, sql, params=None):
    with psycopg2.connect(sync_url(database)) as connection, connection.cursor() as cursor:
        cursor.execute(sql, params)
        rows = cursor.fetchall() if cursor.description else None
    connection.close()
    return rows


def _execute(database, sql, params=None):
    connection = psycopg2.connect(sync_url(database))
    with connection, connection.cursor() as cursor:
        cursor.execute(sql, params)
    connection.close()


def _head():
    result = run_alembic("postgres", "heads")
    return result.stdout.split()[0]


def _revision(database):
    return _query(database, "SELECT version_num FROM alembic_version")[0][0]


def _seed_legacy_bot(database):
    """User, credential and bot as they exist at the legacy revision."""
    now = datetime.now(timezone.utc)
    user_id, credential_id, bot_id = uuid.uuid4(), uuid.uuid4(), uuid.uuid4()
    _execute(database,
             "INSERT INTO users (id, name, email, password, is_active, created_at, updated_at) "
             "VALUES (%s, 'u', %s, 'h', true, %s, %s)",
             (str(user_id), f"{user_id.hex}@test.dev", now, now))
    _execute(database,
             "INSERT INTO exchange_credentials (id, user_id, name, api_key, api_secret, "
             "is_testnet, is_active, created_at, updated_at) "
             "VALUES (%s, %s, 'BYBIT', 'k', 's', true, true, %s, %s)",
             (str(credential_id), str(user_id), now, now))
    _execute(database,
             "INSERT INTO bot_configs (id, user_id, credential_id, name, symbol, strategy_type, "
             "is_active, allocated_capital, stop_loss_pct, take_profit_pct, created_at, updated_at) "
             "VALUES (%s, %s, %s, 'b', 'BTC/USDT', 'RSI_SIMPLE', false, 100, 2, 4, %s, %s)",
             (str(bot_id), str(user_id), str(credential_id), now, now))
    return bot_id


def _insert_legacy_trade(database, bot_id, status, price=50000, quantity=0.002):
    _execute(database,
             "INSERT INTO trades (id, bot_config_id, symbol, side, status, price_executed, "
             "quantity, executed_at) VALUES (%s, %s, 'BTC/USDT', 'BUY', %s, %s, %s, %s)",
             (str(uuid.uuid4()), str(bot_id), status, price, quantity, datetime.now(timezone.utc)))


def test_all_migrations_apply_to_a_clean_database(empty_database):
    result = run_alembic(empty_database, "upgrade", "head")
    assert result.returncode == 0, result.stderr
    assert _revision(empty_database) == _head()

    indexes = {row[0]: row[1] for row in _query(
        empty_database, "SELECT indexname, indexdef FROM pg_indexes WHERE tablename = 'trades'")}
    assert "uq_trades_one_active_per_bot" in indexes
    assert "WHERE" in indexes["uq_trades_one_active_per_bot"]
    columns = {row[0] for row in _query(
        empty_database,
        "SELECT column_name FROM information_schema.columns WHERE table_name = 'trades'")}
    assert {"client_order_id", "entry_context", "exit_client_order_id", "entry_cost"} <= columns


def test_migrations_are_reversible(empty_database):
    assert run_alembic(empty_database, "upgrade", "head").returncode == 0
    down = run_alembic(empty_database, "downgrade", LEGACY_REVISION)
    assert down.returncode == 0, down.stderr
    assert _revision(empty_database) == LEGACY_REVISION
    up = run_alembic(empty_database, "upgrade", "head")
    assert up.returncode == 0, up.stderr


def test_existing_database_is_upgraded_and_legacy_open_trade_backfilled(empty_database):
    assert run_alembic(empty_database, "upgrade", LEGACY_REVISION).returncode == 0
    bot_id = _seed_legacy_bot(empty_database)
    _insert_legacy_trade(empty_database, bot_id, "OPEN", price=50000, quantity=0.002)
    _insert_legacy_trade(empty_database, bot_id, "CLOSED")

    result = run_alembic(empty_database, "upgrade", "head")
    assert result.returncode == 0, result.stderr

    rows = _query(empty_database,
                  "SELECT status, open_quantity, entry_cost FROM trades ORDER BY status DESC")
    open_row = [r for r in rows if r[0] == "OPEN"][0]
    assert float(open_row[1]) == 0.002
    assert float(open_row[2]) == 100.0
    closed_row = [r for r in rows if r[0] == "CLOSED"][0]
    assert closed_row[1] is None  # only active legacy trades are backfilled


def test_upgrade_fails_atomically_with_duplicate_open_trades(empty_database):
    assert run_alembic(empty_database, "upgrade", LEGACY_REVISION).returncode == 0
    bot_id = _seed_legacy_bot(empty_database)
    _insert_legacy_trade(empty_database, bot_id, "OPEN")
    _insert_legacy_trade(empty_database, bot_id, "OPEN")

    result = run_alembic(empty_database, "upgrade", "head")

    assert result.returncode != 0
    assert "uq_trades_one_active_per_bot" in result.stderr
    # PostgreSQL DDL is transactional: nothing of the failed migration remains.
    assert _revision(empty_database) == LEGACY_REVISION
    columns = {row[0] for row in _query(
        empty_database,
        "SELECT column_name FROM information_schema.columns WHERE table_name = 'trades'")}
    assert "client_order_id" not in columns


def test_api_keys_are_encrypted_by_migration_and_restored_on_downgrade(empty_database):
    import os
    from cryptography.fernet import Fernet

    assert run_alembic(empty_database, "upgrade", "b2c3d4e5f6a7").returncode == 0
    user_id, credential_id = uuid.uuid4(), uuid.uuid4()
    now = datetime.now(timezone.utc)
    _execute(empty_database,
             "INSERT INTO users (id, name, email, password, is_active, created_at, updated_at) "
             "VALUES (%s, 'u', %s, 'h', true, %s, %s)", (str(user_id), f"{user_id.hex}@x.dev", now, now))
    _execute(empty_database,
             "INSERT INTO exchange_credentials (id, user_id, name, api_key, api_secret, is_testnet, "
             "is_active, created_at, updated_at) VALUES (%s, %s, 'BYBIT', 'PLAINKEY9876', 's', true, "
             "true, %s, %s)", (str(credential_id), str(user_id), now, now))

    assert run_alembic(empty_database, "upgrade", "head").returncode == 0
    stored, hint = _query(empty_database, "SELECT api_key, api_key_hint FROM exchange_credentials")[0]
    assert stored != "PLAINKEY9876"
    assert Fernet(os.environ["ENCRYPTION_KEY"].encode()).decrypt(stored.encode()) == b"PLAINKEY9876"
    assert hint == "9876"

    # Idempotent: re-running the data step must not double-encrypt.
    assert run_alembic(empty_database, "downgrade", "b2c3d4e5f6a7").returncode == 0
    assert _query(empty_database, "SELECT api_key FROM exchange_credentials")[0][0] == "PLAINKEY9876"
    assert run_alembic(empty_database, "upgrade", "head").returncode == 0
    again = _query(empty_database, "SELECT api_key FROM exchange_credentials")[0][0]
    assert Fernet(os.environ["ENCRYPTION_KEY"].encode()).decrypt(again.encode()) == b"PLAINKEY9876"
