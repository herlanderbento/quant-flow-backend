"""The schema comes only from Alembic migrations: application start-up never creates tables."""
from main import app, lifespan
from shared.infra.db import config


async def test_development_startup_does_not_touch_the_schema(monkeypatch):
    # tests/conftest.py points DATABASE_URL at an unreachable server: any DDL attempt would fail.
    monkeypatch.setattr(config.settings, "ENV", "development")
    async with lifespan(app):
        pass
