from unittest.mock import AsyncMock, MagicMock
from uuid import uuid4

from httpx import ASGITransport, AsyncClient

from account.application.use_cases.credential.create_credential import (
    CreateCredentialUseCase,
)
from account.infra.api.credential.credential_dependencies import (
    get_create_credential_use_case,
)
from main import app
from shared.infra.api.auth_dependencies import AuthContext, require_authenticated
from shared.infra.db.database import engine

API_KEY = "ABCDEFGHIJKLMNOP1234"
API_SECRET = "super-secret-value-123"


async def test_credential_response_never_contains_secret_or_full_key():
    user_repo = AsyncMock()
    user_repo.find_by_id.return_value = object()
    cred_repo = AsyncMock()
    cred_repo.find_active_by_user.return_value = []
    encryption = MagicMock()
    encryption.encrypt.return_value = "gAAAA-encrypted"

    app.dependency_overrides[require_authenticated] = lambda: AuthContext(
        user_id=uuid4(), user=MagicMock()
    )
    app.dependency_overrides[get_create_credential_use_case] = lambda: CreateCredentialUseCase(
        cred_repo, encryption, user_repo
    )
    try:
        async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
            response = await client.post(
                "/credentials",
                json={"name": "BYBIT", "api_key": API_KEY, "api_secret": API_SECRET,
                      "is_testnet": True},
            )
    finally:
        app.dependency_overrides.clear()

    assert response.status_code == 201
    body = response.text
    assert "api_secret" not in response.json()
    assert API_SECRET not in body
    assert "gAAAA-encrypted" not in body
    assert API_KEY not in body
    assert response.json()["api_key"].endswith("1234")


def test_sql_engine_never_logs_bound_parameters():
    assert engine.sync_engine.hide_parameters is True
    assert engine.echo is False  # SQL_ECHO defaults to off
