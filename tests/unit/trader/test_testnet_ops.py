"""Testnet tooling, fully offline: refusals, endpoint checks and the smoke-order flow."""
import re
import time
from pathlib import Path
from unittest.mock import AsyncMock

import pytest

from shared.domain.exceptions import UnsafeCredentialException
from tests.unit.trader.fakes import bybit_order_row, listing, make_fake_bybit
from trader.domain.interface.exchange_gateway_interface import TradingRules
from trader.infra.gateway.bybit_gateway import BybitGateway
from trader.infra.ops import seed_testnet_bot, testnet_order_smoke
from trader.infra.ops.seed_testnet_bot import Refused, check_account

KEY_INFO = {"retCode": 0, "result": {"readOnly": 0, "uta": 1, "permissions": {
    "Wallet": [], "Spot": ["SpotTrade"], "ContractTrade": []}}}


def _testnet_exchange(usdt=1000.0, btc=0.0):
    exchange = make_fake_bybit()
    exchange.set_sandbox_mode(True)
    exchange.privateGetV5UserQueryApi = AsyncMock(return_value=KEY_INFO)
    exchange.fetch_ticker = AsyncMock(return_value={"last": 50000.0, "bid": 49990.0, "ask": 50010.0})
    exchange.fetch_balance = AsyncMock(return_value={"USDT": {"free": usdt}, "BTC": {"free": btc}})
    exchange.fetch_time = AsyncMock(side_effect=lambda: int(time.time() * 1000))
    return exchange


@pytest.fixture
def testnet_mode(monkeypatch):
    monkeypatch.setattr(seed_testnet_bot.settings, "TRADING_MODE", "testnet")
    monkeypatch.setattr(seed_testnet_bot.settings, "LIVE_TRADING_ENABLED", False)
    monkeypatch.setenv("BYBIT_TESTNET_API_KEY", "tk-abcd")
    monkeypatch.setenv("BYBIT_TESTNET_API_SECRET", "ts-secret-value")


@pytest.mark.parametrize("mode, live", [("paper", False), ("live", True), ("testnet", True)])
async def test_seed_refuses_outside_a_pure_testnet_mode(monkeypatch, mode, live):
    monkeypatch.setattr(seed_testnet_bot.settings, "TRADING_MODE", mode)
    monkeypatch.setattr(seed_testnet_bot.settings, "LIVE_TRADING_ENABLED", live)
    with pytest.raises(Refused):
        await seed_testnet_bot.run(seed_testnet_bot.parse(["--check", "--symbol", "BTC/USDT"]),
                                   gateway_factory=lambda k, s: pytest.fail("must not connect"))


async def test_seed_refuses_without_testnet_keys(monkeypatch, testnet_mode):
    monkeypatch.delenv("BYBIT_TESTNET_API_SECRET")
    with pytest.raises(Refused, match="BYBIT_TESTNET_API_SECRET"):
        await seed_testnet_bot.run(seed_testnet_bot.parse(["--check", "--symbol", "BTC/USDT"]),
                                   gateway_factory=lambda k, s: pytest.fail("must not connect"))


async def test_check_refuses_a_production_endpoint():
    exchange = _testnet_exchange()
    exchange.set_sandbox_mode(False)
    gateway = BybitGateway("", "", exchange=exchange)
    try:
        with pytest.raises(Refused, match="not the Bybit testnet"):
            await check_account(gateway, ["BTC/USDT"], 20.0)
        exchange.privateGetV5UserQueryApi.assert_not_called()
    finally:
        await exchange.close()


async def test_check_refuses_a_classic_account():
    exchange = _testnet_exchange()
    exchange.privateGetV5UserQueryApi.return_value = {"retCode": 0, "result": {
        **KEY_INFO["result"], "uta": 0}}
    gateway = BybitGateway("", "", exchange=exchange)
    try:
        with pytest.raises(UnsafeCredentialException, match="Unified"):
            await check_account(gateway, ["BTC/USDT"], 20.0)
    finally:
        await exchange.close()


async def test_check_refuses_capital_below_the_minimum_order():
    exchange = _testnet_exchange()
    gateway = BybitGateway("", "", exchange=exchange)
    try:
        with pytest.raises(Refused, match="below the BTC/USDT minimum"):
            await check_account(gateway, ["BTC/USDT"], 4.0)  # min order value is 5 USDT
    finally:
        await exchange.close()


async def test_check_passes_and_prints_no_secret(capsys):
    exchange = _testnet_exchange()
    gateway = BybitGateway("tk-abcd", "ts-secret-value", exchange=exchange)
    try:
        await check_account(gateway, ["BTC/USDT"], 20.0)
    finally:
        await exchange.close()
    out = capsys.readouterr().out
    assert "api-testnet.bybit.com" in out and "unified trading account" in out
    assert "ts-secret-value" not in out and "tk-abcd" not in out


def test_smoke_quantity_is_above_both_minimums_and_on_the_step():
    rules = TradingRules(amount_step=0.000001, min_amount=0.000048, min_cost=5.0)
    quantity = testnet_order_smoke.minimum_quantity(rules, 50000.0)
    assert quantity == pytest.approx(0.00012)  # 5 USDT * 1.2 / 50 000
    assert rules.is_tradable(quantity, 50000.0)
    assert round(quantity / 0.000001, 6).is_integer()


async def test_smoke_buys_then_sells_what_is_actually_held():
    exchange = _testnet_exchange()
    rows = {}

    async def create_order(symbol, type_, side, amount, price, params):
        cid = params["clientOrderId"]
        assert params["marketUnit"] == "baseCoin" and len(cid) <= 36
        fee = {"BTC": "0.00000012"} if side == "buy" else {"USDT": "0.006"}
        rows[cid] = bybit_order_row(order_id=f"o-{side}", client_order_id=cid,
                                    side=side.capitalize(), qty=str(amount), filled=str(amount),
                                    avg_price="50000", fee=fee)
        return {"id": f"o-{side}", "info": {}}

    async def realtime(request):
        return listing(rows[request["orderLinkId"]]) if request["orderLinkId"] in rows else listing()

    exchange.create_order = AsyncMock(side_effect=create_order)
    exchange.privateGetV5OrderRealtime = AsyncMock(side_effect=realtime)
    gateway = BybitGateway("", "", exchange=exchange, order_poll_delay_seconds=0)
    try:
        await testnet_order_smoke.smoke(gateway, "BTC/USDT")
    finally:
        await exchange.close()

    (buy, sell) = [c.args for c in exchange.create_order.call_args_list]
    assert buy[2] == "buy" and buy[3] == pytest.approx(0.00012)
    # Sells the bought quantity minus the fee charged in BTC, floored to the step.
    assert sell[2] == "sell" and sell[3] == pytest.approx(0.000119)


async def test_smoke_refuses_without_enough_quote_balance():
    exchange = _testnet_exchange(usdt=1.0)
    gateway = BybitGateway("", "", exchange=exchange)
    try:
        with pytest.raises(Refused, match="balance"):
            await testnet_order_smoke.smoke(gateway, "BTC/USDT")
        exchange.create_order.assert_not_called()
    finally:
        await exchange.close()


def test_smoke_cli_requires_explicit_confirmation(monkeypatch):
    monkeypatch.setattr("sys.argv", ["smoke", "--symbol", "BTC/USDT"])
    with pytest.raises(SystemExit) as exit_info:
        testnet_order_smoke.main()
    assert exit_info.value.code == 2




async def test_check_refuses_a_skewed_clock():
    exchange = _testnet_exchange()
    exchange.fetch_time = AsyncMock(side_effect=lambda: int(time.time() * 1000) + 10_000)
    gateway = BybitGateway("", "", exchange=exchange)
    try:
        with pytest.raises(Refused, match="clock"):
            await check_account(gateway, ["BTC/USDT"], 20.0)
        exchange.privateGetV5UserQueryApi.assert_not_called()
    finally:
        await exchange.close()


async def test_check_refuses_missing_instrument_filters():
    exchange = _testnet_exchange()
    exchange.markets["BTC/USDT"]["limits"]["cost"]["min"] = None
    gateway = BybitGateway("", "", exchange=exchange)
    try:
        with pytest.raises(Refused, match="min_cost"):
            await check_account(gateway, ["BTC/USDT"], 20.0)
    finally:
        await exchange.close()


def test_testnet_stack_blocks_mainnet_hosts_at_network_level():
    compose = (Path(__file__).resolve().parents[3] / "docker-compose.testnet.yml").read_text()
    for host in ("api.bybit.com", "api.bytick.com"):
        assert f'"{host}:0.0.0.0"' in compose
    services_with_block = re.findall(r"\n  (\w+):\n    extra_hosts: \*block-mainnet", compose)
    assert set(services_with_block) == {"testnet_worker", "testnet_tools"}
