"""HTTP API against real PostgreSQL: registration, login, ownership, deactivation."""
import pytest
from httpx import ASGITransport, AsyncClient
from sqlalchemy import text

from main import app
from shared.infra.db.database import get_db_session

PASSWORD = "integration-only-password"


@pytest.fixture
async def api(session_factory):
    async def db_session():
        # Same transaction semantics as shared.infra.db.database.get_db_session.
        async with session_factory() as session:
            try:
                yield session
                await session.commit()
            except Exception:
                await session.rollback()
                raise

    app.dependency_overrides[get_db_session] = db_session
    yield
    for open_client in _clients:
        await open_client.aclose()
    _clients.clear()
    app.dependency_overrides.clear()


_clients: list[AsyncClient] = []


def client() -> AsyncClient:
    # https so Secure cookies are sent back, as in production.
    new_client = AsyncClient(transport=ASGITransport(app=app), base_url="https://test")
    _clients.append(new_client)
    return new_client


async def register_and_login(name: str):
    c = client()
    email = f"{name}@quantflow.dev"
    created = await c.post("/users", json={"name": name, "email": email, "password": PASSWORD})
    assert created.status_code == 201, created.text
    login = await c.post("/auth/login", json={"email": email, "password": PASSWORD})
    assert login.status_code == 200, login.text
    return c, created.json()["id"], email


async def test_database_connectivity(session_factory):
    async with session_factory() as session:
        assert (await session.execute(text("SELECT 1"))).scalar_one() == 1


async def test_ownership_is_enforced_with_real_data(api):
    alice, alice_id, _ = await register_and_login("alice")
    bob, bob_id, _ = await register_and_login("bob")
    assert (await alice.get(f"/users/{alice_id}")).status_code == 200
    assert (await alice.get(f"/users/{bob_id}")).status_code == 403
    assert (await alice.patch(f"/users/{bob_id}", json={"password": "pwned"})).status_code == 403
    assert (await alice.delete(f"/users/{bob_id}")).status_code == 403

    created = await alice.post("/credentials", json={
        "name": "BYBIT", "api_key": "INTEGRATIONKEY0001",
        "api_secret": "integration-secret", "is_testnet": True})
    assert created.status_code == 201
    body = created.json()
    assert "api_secret" not in body
    assert body["api_key"].endswith("0001")
    assert "INTEGRATIONKEY0001" not in created.text
    credential_id = body["id"]

    listed_by_bob = await bob.get("/credentials/user")
    assert listed_by_bob.status_code == 200
    assert listed_by_bob.json()["data"] == []
    assert (await bob.delete(f"/credentials/{credential_id}")).status_code == 403
    assert (await alice.delete(f"/credentials/{credential_id}")).status_code == 204


async def test_deactivated_user_loses_access(api):
    carol, carol_id, email = await register_and_login("carol")
    assert (await carol.patch(f"/users/{carol_id}", json={"is_active": False})).status_code == 200
    assert (await carol.get(f"/users/{carol_id}")).status_code == 401  # existing session
    assert (await carol.post("/auth/refresh")).status_code == 401
    relogin = await carol.post("/auth/login", json={"email": email, "password": PASSWORD})
    assert relogin.status_code == 401


async def test_wrong_password_is_rejected(api):
    dave, _, email = await register_and_login("dave")
    response = await dave.post("/auth/login", json={"email": email, "password": "wrong"})
    assert response.status_code == 401


async def test_user_listing_never_exposes_other_users(api):
    erin, erin_id, _ = await register_and_login("erin")
    await register_and_login("frank")
    response = await erin.get("/users", params={"per_page": 100})
    assert response.status_code == 200
    ids = [user["id"] for user in response.json()["data"]]
    assert ids == [erin_id]
    assert "frank@quantflow.dev" not in response.text


async def test_api_key_is_stored_encrypted(api, session_factory):
    from sqlalchemy import text
    gina, _, _ = await register_and_login("gina")
    created = await gina.post("/credentials", json={
        "name": "BYBIT", "api_key": "GINAKEY00004321", "api_secret": "s", "is_testnet": True})
    assert created.status_code == 201
    assert created.json()["api_key"] == "************4321"
    async with session_factory() as session:
        stored = (await session.execute(text("SELECT api_key FROM exchange_credentials"))).scalar_one()
    assert "GINAKEY" not in stored
