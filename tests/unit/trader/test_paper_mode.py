from unittest.mock import AsyncMock, MagicMock

import pytest

from account.domain.credential import Credential
from account.domain.user import UserId
from shared.domain.exceptions import OrderRejectedException, TradingModeException
from shared.infra.db.config import Settings
from tests.unit.trader.fakes import make_fake_bybit
from trader.infra.gateway.bybit_gateway import BybitGateway
from trader.infra.gateway.gateway_factory import create_trading_gateway
from trader.infra.gateway.paper_gateway import PaperExchangeGateway


def _credential(is_testnet: bool) -> Credential:
    return Credential(
        user_id=UserId(),
        name="BYBIT",
        api_key="real-looking-key",
        api_secret="encrypted-secret",
        is_testnet=is_testnet,
        is_active=True,
    )


def _factory(mode, live_enabled=False, is_testnet=False, decrypt=None):
    return create_trading_gateway(
        trading_mode=mode,
        live_trading_enabled=live_enabled,
        credential=_credential(is_testnet),
        decrypt_secret=decrypt or MagicMock(return_value="plain"),
        paper_taker_fee_rate=0.001,
        paper_slippage_bps=5,
    )


class TestDefaults:
    def test_default_trading_mode_is_paper_and_live_disabled(self, monkeypatch):
        monkeypatch.delenv("TRADING_MODE", raising=False)
        monkeypatch.delenv("LIVE_TRADING_ENABLED", raising=False)
        settings = Settings(_env_file=None, DATABASE_URL="x", ENCRYPTION_KEY="x", JWT_SECRET_KEY="x")
        assert settings.TRADING_MODE == "paper"
        assert settings.LIVE_TRADING_ENABLED is False

    def test_unknown_mode_is_rejected_by_settings(self):
        with pytest.raises(ValueError):
            Settings(_env_file=None, DATABASE_URL="x", ENCRYPTION_KEY="x",
                     JWT_SECRET_KEY="x", TRADING_MODE="yolo")


class TestGatewayFactory:
    async def test_paper_mode_uses_keyless_gateway_and_never_decrypts(self):
        decrypt = MagicMock()
        gateway = _factory("paper", decrypt=decrypt)
        try:
            assert isinstance(gateway, PaperExchangeGateway)
            assert not gateway.market_data.exchange.apiKey
            assert not gateway.market_data.exchange.secret
            decrypt.assert_not_called()
        finally:
            await gateway.close()

    async def test_paper_mode_ignores_mainnet_credential(self):
        gateway = _factory("paper", is_testnet=False, live_enabled=True)
        try:
            assert isinstance(gateway, PaperExchangeGateway)
        finally:
            await gateway.close()

    def test_testnet_mode_refuses_mainnet_credential(self):
        with pytest.raises(TradingModeException):
            _factory("testnet", is_testnet=False)

    async def test_testnet_mode_uses_sandbox(self):
        gateway = _factory("testnet", is_testnet=True)
        try:
            assert isinstance(gateway, BybitGateway)
            assert "testnet" in str(gateway.exchange.urls["api"])
        finally:
            await gateway.close()

    async def test_each_mode_resolves_only_its_own_endpoint(self):
        testnet = _factory("testnet", is_testnet=True)
        live = _factory("live", live_enabled=True, is_testnet=False)
        paper = _factory("paper")
        try:
            assert testnet.api_hosts() == {"api-testnet.bybit.com"}
            assert live.api_hosts() == {"api.bybit.com"}
            # Paper reads public market data only, with no keys at all.
            assert paper.market_data.api_hosts() == {"api.bybit.com"}
        finally:
            for gateway in (testnet, live, paper):
                await gateway.close()

    async def test_factory_passes_the_tradable_list_to_every_mode(self):
        symbols = frozenset({"ETH/USDT"})
        gateways = [
            create_trading_gateway(trading_mode=mode, live_trading_enabled=live,
                                   credential=_credential(testnet), decrypt_secret=MagicMock(return_value="p"),
                                   paper_taker_fee_rate=0.001, paper_slippage_bps=5, tradable_symbols=symbols)
            for mode, live, testnet in (("paper", False, False), ("testnet", False, True), ("live", True, False))
        ]
        try:
            assert gateways[0].market_data.tradable_symbols == symbols
            assert gateways[1].tradable_symbols == symbols
            assert gateways[2].tradable_symbols == symbols
        finally:
            for gateway in gateways:
                await gateway.close()

    def test_live_mode_requires_explicit_enable_flag(self):
        with pytest.raises(TradingModeException):
            _factory("live", live_enabled=False)

    def test_live_mode_refuses_testnet_credential(self):
        with pytest.raises(TradingModeException):
            _factory("live", live_enabled=True, is_testnet=True)


@pytest.fixture
async def paper():
    exchange = make_fake_bybit()
    exchange.fetch_ticker = AsyncMock(return_value={"bid": 49990.0, "ask": 50010.0, "last": 50000.0})
    gateway = PaperExchangeGateway(
        BybitGateway("", "", exchange=exchange), taker_fee_rate=0.001, slippage_bps=10
    )
    yield gateway, exchange
    await exchange.close()


class TestPaperExecution:
    async def test_buy_fills_at_ask_plus_slippage_with_base_fee(self, paper):
        gateway, exchange = paper
        result = await gateway.place_market_order("BTC/USDT", "BUY", 0.01, "cid-1")

        assert result.average_price == pytest.approx(50010.0 * 1.001)
        assert result.filled_quantity == pytest.approx(0.01)
        assert result.fee_currency == "BTC"
        assert result.net_base_quantity("BTC") == pytest.approx(0.01 * 0.999)
        exchange.create_order.assert_not_called()

    async def test_sell_fills_at_bid_minus_slippage_with_quote_fee(self, paper):
        gateway, exchange = paper
        result = await gateway.place_market_order("BTC/USDT", "SELL", 0.01, "cid-2")

        expected_price = 49990.0 * 0.999
        assert result.average_price == pytest.approx(expected_price)
        assert result.fee_currency == "USDT"
        assert result.fee_cost == pytest.approx(0.01 * expected_price * 0.001)
        exchange.create_order.assert_not_called()

    async def test_same_client_id_does_not_fill_twice(self, paper):
        gateway, _ = paper
        first = await gateway.place_market_order("BTC/USDT", "BUY", 0.01, "cid-1")
        second = await gateway.place_market_order("BTC/USDT", "BUY", 0.01, "cid-1")
        assert first is second
        assert await gateway.get_order_by_client_id("BTC/USDT", "cid-1") is first

    async def test_missing_quote_rejects_order(self, paper):
        gateway, exchange = paper
        exchange.fetch_ticker.return_value = {"bid": None, "ask": None, "last": 1.0}
        with pytest.raises(OrderRejectedException):
            await gateway.place_market_order("BTC/USDT", "BUY", 0.01, "cid-3")


async def test_paper_gateway_reports_no_account_balance(paper):
    gateway, exchange = paper
    exchange.fetch_balance = AsyncMock()
    assert await gateway.get_balance("USDT") is None
    exchange.fetch_balance.assert_not_called()
