"""Backend and worker run `alembic upgrade head` on start: migrations must never race."""
import subprocess
import sys
import time

import psycopg2

from shared.infra.db.migration_lock import MIGRATION_LOCK_ID
from tests.integration.conftest import ROOT, _with_database, ADMIN_URL, run_alembic, sync_url


def _alembic_process(database: str) -> subprocess.Popen:
    env = {**__import__("os").environ,
           "DATABASE_URL": _with_database(ADMIN_URL, database, "postgresql+asyncpg"),
           "PYTHONPATH": str(ROOT / "src")}
    return subprocess.Popen([sys.executable, "-m", "alembic", "upgrade", "head"], cwd=ROOT, env=env,
                            stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True)


def _versions(database: str) -> list:
    with psycopg2.connect(sync_url(database)) as connection, connection.cursor() as cursor:
        cursor.execute("SELECT to_regclass('public.alembic_version')")
        if cursor.fetchone()[0] is None:
            return []
        cursor.execute("SELECT version_num FROM alembic_version")
        rows = [r[0] for r in cursor.fetchall()]
    connection.close()
    return rows


def test_upgrade_waits_for_the_migration_lock(empty_database):
    holder = psycopg2.connect(sync_url(empty_database))
    holder.autocommit = True
    with holder.cursor() as cursor:
        cursor.execute("SELECT pg_advisory_lock(%s)", (MIGRATION_LOCK_ID,))
    try:
        process = _alembic_process(empty_database)
        time.sleep(8)
        assert process.poll() is None, process.communicate()[1][-2000:]
        assert _versions(empty_database) == []  # nothing applied while another migrator holds the lock
    finally:
        with holder.cursor() as cursor:
            cursor.execute("SELECT pg_advisory_unlock(%s)", (MIGRATION_LOCK_ID,))
        holder.close()
    _, stderr = process.communicate(timeout=120)
    assert process.returncode == 0, stderr[-2000:]
    assert _versions(empty_database) == [run_alembic("postgres", "heads").stdout.split()[0]]


def test_simultaneous_upgrades_do_not_race(empty_database):
    processes = [_alembic_process(empty_database) for _ in range(3)]
    results = [p.communicate(timeout=180) for p in processes]
    for process, (_, stderr) in zip(processes, results):
        assert process.returncode == 0, stderr[-2000:]
    assert _versions(empty_database) == [run_alembic("postgres", "heads").stdout.split()[0]]
