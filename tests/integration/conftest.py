"""
Integration tests against a real, disposable PostgreSQL server.

Enable with:
    QUANTFLOW_INTEGRATION_DB=postgresql://quantflow_test:quantflow_test@127.0.0.1:55432/postgres

Every test gets its own freshly created database (cloned from a migrated template),
so tests are isolated and nothing persists. The suite refuses to run against a
server that looks like the development/production one.
"""
import os
import subprocess
import sys
import uuid
from pathlib import Path
from urllib.parse import urlsplit, urlunsplit

import psycopg2
import pytest
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from shared.infra.db.database import build_engine

ROOT = Path(__file__).resolve().parents[2]
ADMIN_URL = os.environ.get("QUANTFLOW_INTEGRATION_DB")
FORBIDDEN_DATABASES = {"quantflow_db"}
FORBIDDEN_PORTS = {6000}

pytestmark = pytest.mark.integration


def pytest_collection_modifyitems(config, items):
    if ADMIN_URL:
        return
    skip = pytest.mark.skip(reason="QUANTFLOW_INTEGRATION_DB not set (see tests/integration/conftest.py)")
    for item in items:
        if "integration" in str(item.fspath):
            item.add_marker(skip)


def _with_database(url: str, database: str, driver: str | None = None) -> str:
    parts = urlsplit(url)
    scheme = driver or parts.scheme
    return urlunsplit((scheme, parts.netloc, f"/{database}", "", ""))


def _admin_connection():
    connection = psycopg2.connect(ADMIN_URL)
    connection.autocommit = True
    return connection


def _assert_disposable_server() -> None:
    if urlsplit(ADMIN_URL).port in FORBIDDEN_PORTS:
        pytest.exit("Refusing to run integration tests against the development port 6000.", 2)
    with _admin_connection() as connection, connection.cursor() as cursor:
        cursor.execute("SELECT datname FROM pg_database")
        names = {row[0] for row in cursor.fetchall()}
    connection.close()
    clash = names & FORBIDDEN_DATABASES
    if clash:
        pytest.exit(f"Refusing to run: server hosts {clash}; use the disposable test server.", 2)


def create_database(name: str, template: str | None = None) -> None:
    connection = _admin_connection()
    with connection.cursor() as cursor:
        template_sql = f' TEMPLATE "{template}"' if template else ""
        cursor.execute(f'CREATE DATABASE "{name}"{template_sql}')
    connection.close()


def drop_database(name: str) -> None:
    connection = _admin_connection()
    with connection.cursor() as cursor:
        cursor.execute(
            "SELECT pg_terminate_backend(pid) FROM pg_stat_activity WHERE datname = %s",
            (name,),
        )
        cursor.execute(f'DROP DATABASE IF EXISTS "{name}"')
    connection.close()


def run_alembic(database: str, *args: str) -> subprocess.CompletedProcess:
    """Runs Alembic exactly like deployment does, in a separate process."""
    env = {
        **os.environ,
        "DATABASE_URL": _with_database(ADMIN_URL, database, "postgresql+asyncpg"),
        "PYTHONPATH": str(ROOT / "src"),
    }
    return subprocess.run(
        [sys.executable, "-m", "alembic", *args],
        cwd=ROOT,
        env=env,
        capture_output=True,
        text=True,
        timeout=120,
    )


def new_database_name(prefix: str = "qf_it") -> str:
    return f"{prefix}_{uuid.uuid4().hex[:12]}"


@pytest.fixture(scope="session")
def migrated_template():
    _assert_disposable_server()
    name = new_database_name("qf_template")
    create_database(name)
    result = run_alembic(name, "upgrade", "head")
    assert result.returncode == 0, result.stderr
    yield name
    drop_database(name)


@pytest.fixture
def database_name(migrated_template):
    name = new_database_name()
    create_database(name, template=migrated_template)
    yield name
    drop_database(name)


@pytest.fixture
def empty_database():
    _assert_disposable_server()
    name = new_database_name()
    create_database(name)
    yield name
    drop_database(name)


@pytest.fixture
async def session_factory(database_name):
    engine = build_engine(_with_database(ADMIN_URL, database_name, "postgresql+asyncpg"))
    yield async_sessionmaker(bind=engine, class_=AsyncSession, expire_on_commit=False)
    await engine.dispose()


def sync_url(database: str) -> str:
    return _with_database(ADMIN_URL, database, "postgresql")
