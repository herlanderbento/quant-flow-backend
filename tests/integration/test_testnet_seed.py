"""seed_testnet_bot against real PostgreSQL, with an offline exchange double."""
from unittest.mock import AsyncMock

from sqlalchemy import text

from shared.infra.api.dependencies import get_encryption
from tests.unit.trader.test_testnet_ops import _testnet_exchange
from trader.infra.gateway.bybit_gateway import BybitGateway
from trader.infra.ops import seed_testnet_bot

KEY, SECRET = "testnet-key-wxyz", "testnet-secret-value"


async def _seed(monkeypatch, session_factory, *extra):
    monkeypatch.setattr(seed_testnet_bot.settings, "TRADING_MODE", "testnet")
    monkeypatch.setattr(seed_testnet_bot.settings, "LIVE_TRADING_ENABLED", False)
    monkeypatch.setenv("BYBIT_TESTNET_API_KEY", KEY)
    monkeypatch.setenv("BYBIT_TESTNET_API_SECRET", SECRET)
    monkeypatch.setattr(seed_testnet_bot, "AsyncSessionLocal", session_factory)
    monkeypatch.setattr(seed_testnet_bot, "engine", AsyncMock())
    args = seed_testnet_bot.parse(["--symbol", "BTC/USDT", "--capital", "20", *extra])
    await seed_testnet_bot.run(args, gateway_factory=lambda k, s: BybitGateway(
        k, s, exchange=_testnet_exchange()))


async def test_seed_stores_encrypted_testnet_credential_and_inactive_bots(
        monkeypatch, session_factory, capsys):
    await _seed(monkeypatch, session_factory)

    async with session_factory() as session:
        cred = (await session.execute(text(
            "SELECT api_key, api_secret, api_key_hint, is_testnet, is_active "
            "FROM exchange_credentials"))).one()
        bots = (await session.execute(text("SELECT symbol, is_active FROM bot_configs"))).all()
    assert cred.api_key != KEY and cred.api_secret != SECRET
    assert get_encryption().decrypt(cred.api_key) == KEY
    assert get_encryption().decrypt(cred.api_secret) == SECRET
    assert (cred.api_key_hint, cred.is_testnet, cred.is_active) == ("wxyz", True, True)
    assert [(b.symbol, b.is_active) for b in bots] == [("BTC/USDT", False)]
    out = capsys.readouterr().out
    assert SECRET not in out and KEY not in out


async def test_reseeding_deactivates_the_previous_credential(monkeypatch, session_factory):
    await _seed(monkeypatch, session_factory)
    await _seed(monkeypatch, session_factory, "--activate")

    async with session_factory() as session:
        active = (await session.execute(text(
            "SELECT count(*) FROM exchange_credentials WHERE is_active"))).scalar_one()
        bots = (await session.execute(text(
            "SELECT count(*) FILTER (WHERE is_active) FROM bot_configs"))).scalar_one()
    assert active == 1
    assert bots == 1  # only the bot of the second run, which asked for --activate


async def test_check_only_writes_nothing(monkeypatch, session_factory):
    await _seed(monkeypatch, session_factory, "--check")
    async with session_factory() as session:
        assert (await session.execute(text("SELECT count(*) FROM exchange_credentials"))).scalar_one() == 0
