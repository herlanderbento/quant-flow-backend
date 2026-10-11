"""Fixtures partilhadas para a suíte de testes.

Environment variables take precedence over the `.env` file in pydantic-settings,
so these defaults keep every test away from the developer's real configuration
(database, encryption key, JWT secret) before any application module is imported.
"""
import os

# Unreachable on purpose: nothing may silently fall back to the development database.
os.environ["DATABASE_URL"] = "postgresql+asyncpg://test:test@127.0.0.1:1/never_used"
os.environ["ENCRYPTION_KEY"] = "dGVzdC1vbmx5LWZlcm5ldC1rZXktMzItYnl0ZXMtISE="
os.environ["JWT_SECRET_KEY"] = "test-only-jwt-secret-with-at-least-32-bytes"
os.environ["ENV"] = "test"
os.environ["TRADING_MODE"] = "paper"
os.environ["LIVE_TRADING_ENABLED"] = "false"
os.environ.pop("SQL_ECHO", None)
