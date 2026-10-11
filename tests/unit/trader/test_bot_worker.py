from unittest.mock import AsyncMock, MagicMock

import pytest

from account.domain.credential import Credential
from account.domain.user import UserId
from shared.domain.exceptions import UnsafeCredentialException
from shared.infra.db.config import settings
from trader.infra.gateway.bybit_gateway import BybitGateway
from trader.infra.gateway.paper_gateway import PaperExchangeGateway
from trader.infra.worker import bot_worker


def _settings(mode):
    return settings.model_copy(update={"TRADING_MODE": mode, "LIVE_TRADING_ENABLED": True})


def _credential():
    return Credential(user_id=UserId(), name="BYBIT", api_key="k", api_secret="s",
                      is_testnet=True, is_active=True)


async def test_unsafe_key_is_refused_and_not_cached(monkeypatch):
    real = MagicMock(spec=BybitGateway)
    real.verify_api_key_permissions = AsyncMock(side_effect=UnsafeCredentialException("Withdraw"))
    real.close = AsyncMock()
    monkeypatch.setattr(bot_worker, "settings", _settings("testnet"))
    monkeypatch.setattr(bot_worker, "create_trading_gateway", lambda **_: real)

    worker = bot_worker.BotWorker(MagicMock(), MagicMock())
    with pytest.raises(UnsafeCredentialException):
        await worker._gateway_for(_credential())

    real.close.assert_awaited_once()
    assert worker._gateways == {}


async def test_paper_gateway_is_shared_and_not_verified(monkeypatch):
    monkeypatch.setattr(bot_worker, "settings", _settings("paper"))
    worker = bot_worker.BotWorker(MagicMock(), MagicMock())
    try:
        first = await worker._gateway_for(_credential())
        second = await worker._gateway_for(_credential())
        assert isinstance(first, PaperExchangeGateway)
        assert first is second
    finally:
        await worker.close_gateways()
