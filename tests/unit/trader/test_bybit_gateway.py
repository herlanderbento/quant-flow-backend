from unittest.mock import AsyncMock

import pytest
from ccxt.base.errors import InsufficientFunds, InvalidOrder, RequestTimeout

from shared.domain.exceptions import (
    UnsafeCredentialException,
    GatewayException,
    OrderRejectedException,
    OrderStateUnknownException,
)
from tests.unit.trader.fakes import bybit_order_row, listing, make_fake_bybit
from trader.infra.gateway.bybit_gateway import BybitGateway


@pytest.fixture
async def fake():
    exchange = make_fake_bybit()
    gateway = BybitGateway("", "", exchange=exchange, order_poll_delay_seconds=0)
    yield gateway, exchange
    await exchange.close()


async def test_market_order_reads_back_real_execution(fake):
    gateway, exchange = fake
    exchange.privateGetV5OrderRealtime.return_value = listing(
        bybit_order_row(client_order_id="cid-1", avg_price="50010.5")
    )

    result = await gateway.place_market_order("BTC/USDT", "BUY", 0.002, "cid-1")

    args = exchange.create_order.call_args.args
    assert args[:4] == ("BTC/USDT", "market", "buy", 0.002)
    assert args[5] == {"clientOrderId": "cid-1", "marketUnit": "baseCoin"}
    assert result.status == "closed"
    assert result.average_price == pytest.approx(50010.5)
    assert result.filled_quantity == pytest.approx(0.002)
    assert result.fee_cost == pytest.approx(0.000002)
    assert result.fee_currency == "BTC"
    assert result.client_order_id == "cid-1"
    assert result.net_base_quantity("BTC") == pytest.approx(0.001998)


async def test_falls_back_to_order_history(fake):
    gateway, exchange = fake
    exchange.privateGetV5OrderHistory.return_value = listing(bybit_order_row())

    result = await gateway.get_order_by_client_id("BTC/USDT", "cid-1")

    assert result is not None
    assert result.status == "closed"


async def test_unknown_order_returns_none(fake):
    gateway, _ = fake
    assert await gateway.get_order_by_client_id("BTC/USDT", "missing") is None


async def test_unconfirmed_order_raises_state_unknown(fake):
    gateway, _ = fake  # create succeeds, but the order never shows up

    with pytest.raises(OrderStateUnknownException):
        await gateway.place_market_order("BTC/USDT", "BUY", 0.002, "cid-1")


async def test_timeout_on_create_is_state_unknown_not_rejected(fake):
    gateway, exchange = fake
    exchange.create_order.side_effect = RequestTimeout("timeout")

    with pytest.raises(OrderStateUnknownException):
        await gateway.place_market_order("BTC/USDT", "BUY", 0.002, "cid-1")


@pytest.mark.parametrize("error", [InsufficientFunds("no money"), InvalidOrder("bad qty")])
async def test_definitive_errors_are_rejections(fake, error):
    gateway, exchange = fake
    exchange.create_order.side_effect = error

    with pytest.raises(OrderRejectedException):
        await gateway.place_market_order("BTC/USDT", "BUY", 0.002, "cid-1")


async def test_partial_fill_then_cancel_is_reported(fake):
    gateway, exchange = fake
    exchange.privateGetV5OrderRealtime.return_value = listing(
        bybit_order_row(status="PartiallyFilledCanceled", qty="0.002", filled="0.001")
    )

    result = await gateway.place_market_order("BTC/USDT", "BUY", 0.002, "cid-1")

    assert result.is_final
    assert result.filled_quantity == pytest.approx(0.001)
    assert result.requested_quantity == pytest.approx(0.002)


async def test_trading_rules_come_from_market_metadata(fake):
    gateway, _ = fake
    rules = await gateway.get_trading_rules("BTC/USDT")
    assert rules.amount_step == 0.000001
    assert rules.min_amount == 0.000048
    assert rules.min_cost == 5.0


async def test_quantity_is_truncated_to_precision_before_sending(fake):
    gateway, exchange = fake
    exchange.privateGetV5OrderRealtime.return_value = listing(bybit_order_row())
    await gateway.place_market_order("BTC/USDT", "SELL", 0.0019989999, "cid-1")
    assert exchange.create_order.call_args.args[3] == 0.001998


async def test_quantity_below_lot_step_is_rejected_without_sending(fake):
    gateway, exchange = fake
    with pytest.raises(OrderRejectedException):
        await gateway.place_market_order("BTC/USDT", "SELL", 0.0000001, "cid-1")
    exchange.create_order.assert_not_called()


HOUR_MS = 3_600_000


def _candles(n, last_open_ms):
    return [[last_open_ms - (n - 1 - i) * HOUR_MS, 100, 101, 99, 100 + i % 3, 1] for i in range(n)]


async def test_snapshot_ignores_the_still_open_candle():
    from unittest.mock import AsyncMock

    exchange = make_fake_bybit()
    now = 1_700_000_000_000
    current_open = now - now % HOUR_MS
    rows = _candles(64, current_open)
    rows[-1][4] = 1_000_000  # absurd close on the forming candle
    exchange.fetch_ohlcv = AsyncMock(return_value=rows)
    exchange.fetch_ticker = AsyncMock(return_value={"last": 100.0})
    gateway = BybitGateway("", "", exchange=exchange, clock_ms=lambda: now)
    try:
        snapshot = await gateway.get_market_snapshot("BTC/USDT")
        assert snapshot.candle_closed_at.timestamp() * 1000 == current_open
        assert snapshot.indicators["rsi"] < 100  # the 1,000,000 close was not used
    finally:
        await exchange.close()


async def test_snapshot_refuses_stale_data():
    from unittest.mock import AsyncMock

    exchange = make_fake_bybit()
    now = 1_700_000_000_000
    exchange.fetch_ohlcv = AsyncMock(return_value=_candles(64, now - 5 * HOUR_MS))
    exchange.fetch_ticker = AsyncMock(return_value={"last": 100.0})
    gateway = BybitGateway("", "", exchange=exchange, clock_ms=lambda: now)
    try:
        with pytest.raises(GatewayException, match="Stale"):
            await gateway.get_market_snapshot("BTC/USDT")
    finally:
        await exchange.close()



def _key_info(wallet=(), spot=("SpotTrade",), read_only=0, uta=1, extra=None):
    result = {"readOnly": read_only, "permissions": {
        "Wallet": list(wallet), "Spot": list(spot), "ContractTrade": [], "Options": [],
        "Derivatives": [], **(extra or {})}}
    if uta is not None:
        result["uta"] = uta
    return {"retCode": 0, "result": result}


@pytest.mark.parametrize("info, reason", [
    (_key_info(wallet=["Withdraw"]), "withdrawal"),
    (_key_info(wallet=["AccountTransfer"]), "transfer between accounts"),
    (_key_info(wallet=["SubMemberTransfer"]), "transfer to sub-members"),
    (_key_info(wallet=["AccountTransfer", "SubMemberTransfer"]), "both transfers"),
    (_key_info(extra={"Earn": ["Earn"]}), "moves funds into earn products"),
    (_key_info(extra={"Exchange": ["ExchangeHistory"]}), "convert"),
    (_key_info(extra={"FiatP2P": ["FiatP2POrder"]}), "fiat payments"),
    (_key_info(extra={"Affiliate": ["Affiliate"]}), "affiliate management"),
    (_key_info(read_only=1), "read-only key cannot place orders"),
    (_key_info(spot=()), "SpotTrade missing"),
    (_key_info(spot=(), extra={"Derivatives": ["DerivativesTrade"]}), "bundled permission without SpotTrade"),
    (_key_info(uta=0), "classic account: market BUY qty read as quote"),
    (_key_info(uta=None), "unknown account type: fail closed"),
    (_key_info(uta=0, extra={"Derivatives": ["DerivativesTrade"]}), "DerivativesTrade tolerated only on UTA"),
    (_key_info(extra={"Stocks": ["StocksTrade"]}), "StocksTrade is not documented by Bybit"),
    (_key_info(extra={"Derivatives": ["DerivativesTrade"], "Stocks": ["StocksTrade"]}), "one undocumented permission is enough"),
    (_key_info(extra={"ContractTrade": ["Order", "Position"]}), "contract trading is not bundled"),
    (_key_info(extra={"Options": ["OptionsTrade"]}), "options trading is not bundled"),
    (_key_info(extra={"BlockTrade": ["BlockTrade"]}), "block trading is not bundled"),
    (_key_info(spot=("SpotTrade", "SpotMarginTrade")), "unknown value in the Spot group"),
    (_key_info(extra={"Derivatives": ["DerivativesTrade", "DerivativesTransfer"]}), "unknown value in a tolerated group"),
    (_key_info(extra={"BrandNewGroup": ["Anything"]}), "unknown group"),
])
async def test_unsafe_or_unusable_api_keys_are_refused(fake, info, reason):
    gateway, exchange = fake
    exchange.privateGetV5UserQueryApi = AsyncMock(return_value=info)
    with pytest.raises(UnsafeCredentialException):
        await gateway.verify_api_key_permissions()


async def test_spot_trade_only_key_is_accepted(fake):
    gateway, exchange = fake
    exchange.privateGetV5UserQueryApi = AsyncMock(return_value=_key_info())
    assert await gateway.verify_api_key_permissions() == [("Spot", "SpotTrade")]


async def test_uta_bundled_derivatives_permission_is_tolerated_on_a_uta(fake):
    gateway, exchange = fake
    exchange.privateGetV5UserQueryApi = AsyncMock(
        return_value=_key_info(extra={"Derivatives": ["DerivativesTrade"]}))
    assert await gateway.verify_api_key_permissions() == [
        ("Derivatives", "DerivativesTrade"), ("Spot", "SpotTrade")]


async def test_tolerated_permission_does_not_open_derivative_markets(fake):
    """A key that could trade derivatives still cannot be used for them: spot markets only."""
    gateway, exchange = fake
    exchange.privateGetV5UserQueryApi = AsyncMock(
        return_value=_key_info(extra={"Derivatives": ["DerivativesTrade"]}))
    await gateway.verify_api_key_permissions()
    with pytest.raises(GatewayException, match="not in the tradable list"):
        await gateway.place_market_order("BTC/USDT:USDT", "BUY", 0.001, "cid-perp")
    # Even if someone listed the perpetual as tradable, only spot markets are loaded.
    gateway.tradable_symbols = frozenset({"BTC/USDT:USDT"})
    with pytest.raises(GatewayException, match="not available"):
        await gateway.place_market_order("BTC/USDT:USDT", "BUY", 0.001, "cid-perp")
    exchange.create_order.assert_not_called()


async def test_live_client_loads_spot_markets_only():
    gateway = BybitGateway("k", "s", is_testnet=False)
    try:
        assert gateway.exchange.options["defaultType"] == "spot"
        assert gateway.exchange.options["fetchMarkets"]["types"] == ["spot"]
    finally:
        await gateway.close()


@pytest.mark.parametrize("is_testnet, host", [(True, "api-testnet.bybit.com"), (False, "api.bybit.com")])
async def test_permission_check_never_changes_the_endpoint(is_testnet, host):
    gateway = BybitGateway("k", "s", is_testnet=is_testnet)
    gateway.exchange.privateGetV5UserQueryApi = AsyncMock(
        return_value=_key_info(extra={"Derivatives": ["DerivativesTrade"]}))
    try:
        await gateway.verify_api_key_permissions()
        assert gateway.api_hosts() == {host}
    finally:
        await gateway.close()


async def test_unverifiable_api_key_is_refused(fake):
    gateway, exchange = fake
    exchange.privateGetV5UserQueryApi = AsyncMock(side_effect=RuntimeError("401"))
    with pytest.raises(UnsafeCredentialException):
        await gateway.verify_api_key_permissions()


async def test_history_pagination_continues_past_short_pages():
    """Bybit returns at most 999 candles per page; a short page is not the end."""
    exchange = make_fake_bybit()
    start = 1_600_000_000_000
    total = 2500
    all_rows = [[start + i * HOUR_MS, 1, 1, 1, 1, 1] for i in range(total)]

    async def fetch_ohlcv(symbol, timeframe, since, limit):
        first = (since - start + HOUR_MS - 1) // HOUR_MS
        return all_rows[first:first + 999]

    exchange.fetch_ohlcv = fetch_ohlcv
    gateway = BybitGateway("", "", exchange=exchange)
    try:
        rows = await gateway.fetch_ohlcv_history(
            "BTC/USDT", "1h", start, start + (total - 1) * HOUR_MS)
    finally:
        await exchange.close()
    assert len(rows) == total
    assert [r[0] for r in rows] == sorted({r[0] for r in rows})


async def test_trading_rules_include_per_order_maximums(fake):
    gateway, exchange = fake
    exchange.markets["BTC/USDT"]["info"] = {"lotSizeFilter": {"maxMarketOrderQty": "12.5"}}
    exchange.markets["BTC/USDT"]["limits"]["cost"]["max"] = 2_000_000.0
    rules = await gateway.get_trading_rules("BTC/USDT")
    assert rules.max_amount == 12.5  # market-order cap wins over the generic limit (71)
    assert rules.max_cost == 2_000_000.0


async def test_generic_amount_maximum_is_used_without_a_market_order_cap(fake):
    gateway, _ = fake
    rules = await gateway.get_trading_rules("BTC/USDT")
    assert rules.max_amount == 71.0
    assert rules.max_cost is None


@pytest.mark.parametrize("is_testnet, host", [(True, "api-testnet.bybit.com"), (False, "api.bybit.com")])
async def test_endpoint_is_resolved_explicitly(is_testnet, host):
    gateway = BybitGateway("k", "s", is_testnet=is_testnet)
    try:
        assert gateway.api_hosts() == {host}
    finally:
        await gateway.close()


async def test_testnet_gateway_refuses_a_production_endpoint(monkeypatch):
    import ccxt.async_support as ccxt
    # Simulates a library/option change that would leave the client on production.
    monkeypatch.setattr(ccxt.bybit, "set_sandbox_mode", lambda self, enabled: None)
    with pytest.raises(UnsafeCredentialException, match="endpoint mismatch"):
        BybitGateway("k", "s", is_testnet=True)


@pytest.mark.parametrize("symbol_type", ["xstocks", "mstocks", "adventure", "something-new"])
async def test_non_crypto_spot_instruments_are_refused_before_any_request(fake, symbol_type):
    """Tokenised stocks are listed as spot pairs on Bybit: they must never be traded."""
    gateway, exchange = fake
    exchange.markets["BTC/USDT"]["info"] = {"symbolType": symbol_type}
    with pytest.raises(GatewayException, match="not a standard crypto spot pair"):
        await gateway.place_market_order("BTC/USDT", "BUY", 0.001, "cid-x")
    with pytest.raises(GatewayException, match="not a standard crypto spot pair"):
        await gateway.get_trading_rules("BTC/USDT")
    exchange.create_order.assert_not_called()


@pytest.mark.parametrize("info", [{}, {"symbolType": ""}, {"symbolType": None}])
async def test_standard_crypto_spot_pair_is_allowed(fake, info):
    gateway, exchange = fake
    exchange.markets["BTC/USDT"]["info"] = info
    rules = await gateway.get_trading_rules("BTC/USDT")
    assert rules.min_cost == 5.0


async def test_symbols_outside_the_tradable_list_are_never_sized_or_ordered():
    exchange = make_fake_bybit()
    gateway = BybitGateway("", "", exchange=exchange, order_poll_delay_seconds=0,
                           tradable_symbols=frozenset({"ETH/USDT"}))
    try:
        with pytest.raises(GatewayException, match="not in the tradable list"):
            await gateway.get_trading_rules("BTC/USDT")
        with pytest.raises(GatewayException, match="not in the tradable list"):
            await gateway.place_market_order("BTC/USDT", "BUY", 0.001, "cid-1")
        exchange.create_order.assert_not_called()
        exchange.load_markets.assert_not_called()  # refused before any exchange request
    finally:
        await exchange.close()


async def test_reconciliation_is_not_blocked_by_the_tradable_list():
    """An order placed earlier must stay reconcilable even if its symbol is delisted from the list."""
    exchange = make_fake_bybit()
    exchange.privateGetV5OrderRealtime.return_value = listing(bybit_order_row(client_order_id="cid-1"))
    gateway = BybitGateway("", "", exchange=exchange, tradable_symbols=frozenset())
    try:
        order = await gateway.get_order_by_client_id("BTC/USDT", "cid-1")
        assert order is not None and order.is_final
    finally:
        await exchange.close()


def test_default_tradable_symbols_are_btc_and_eth_only():
    from trader.infra.gateway.bybit_gateway import DEFAULT_TRADABLE_SYMBOLS
    assert DEFAULT_TRADABLE_SYMBOLS == {"BTC/USDT", "ETH/USDT"}


def test_tradable_symbols_setting_is_parsed_strictly():
    from shared.infra.db.config import Settings
    settings = Settings(_env_file=None, DATABASE_URL="x", ENCRYPTION_KEY="x", JWT_SECRET_KEY="x",
                        TRADABLE_SYMBOLS=" btc/usdt , ETH/USDT,, ")
    assert settings.tradable_symbols == {"BTC/USDT", "ETH/USDT"}
