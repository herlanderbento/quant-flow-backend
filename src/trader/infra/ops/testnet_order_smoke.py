"""One minimum-size market BUY and its closing SELL on the Bybit **testnet**, with read-back.

    python -m trader.infra.ops.testnet_order_smoke --symbol BTC/USDT --confirm-testnet

Validates the order path against the real testnet API: request format, clientOrderId,
execution read-back (realtime/history), fees and closing the position. Nothing is stored.
Refuses unless TRADING_MODE=testnet, LIVE_TRADING_ENABLED=false, the endpoint is the testnet
and the read-only checks of seed_testnet_bot pass. Keys come from the environment
(BYBIT_TESTNET_API_KEY / BYBIT_TESTNET_API_SECRET) and are never printed.
"""
import argparse
import asyncio
import sys
from decimal import ROUND_CEILING, Decimal
from uuid import uuid4

from shared.infra.db.config import settings
from trader.infra.gateway.bybit_gateway import BybitGateway
from trader.infra.ops.seed_testnet_bot import (
    Refused,
    check_account,
    read_keys,
    refuse_unless_testnet_mode,
)

SIZE_MARGIN = 1.2  # above the minimum, so rounding and price moves keep both legs valid


def smoke_client_order_id() -> str:
    return f"qfsmoke{uuid4().hex[:24]}"  # 31 characters; Bybit allows 36


def minimum_quantity(rules, price: float) -> float:
    value = max(rules.min_cost or 0.0, (rules.min_amount or 0.0) * price) * SIZE_MARGIN
    quantity = Decimal(str(value)) / Decimal(str(price))
    if rules.amount_step:
        step = Decimal(str(rules.amount_step))
        # Decimal, not float: 0.00012 / 0.000001 must be 120 steps, not 120.00000000000001.
        steps = (quantity / step).quantize(Decimal("1e-9")).to_integral_value(rounding=ROUND_CEILING)
        quantity = steps * step
    return float(quantity)


def describe(label, order) -> str:
    return (f"{label}: id={order.order_id} cid={order.client_order_id} status={order.status} "
            f"requested={order.requested_quantity} filled={order.filled_quantity} "
            f"avg={order.average_price} fee={order.fee_cost} {order.fee_currency}")


async def smoke(gateway: BybitGateway, symbol: str) -> None:
    base, quote = symbol.split("/", 1)
    rules = await gateway.get_trading_rules(symbol)
    price = await gateway.get_current_price(symbol)
    quantity = minimum_quantity(rules, price)
    if rules.limit_quantity(quantity, price) < quantity or not rules.is_tradable(quantity, price):
        raise Refused(f"computed quantity {quantity} does not fit the instrument limits")
    available = await gateway.get_balance(quote)
    if available is None or available < quantity * price * 1.02:
        raise Refused(f"testnet {quote} balance {available} is too low for {quantity} {base}")
    base_before = await gateway.get_balance(base) or 0.0
    print(f"BUY {quantity} {symbol} (≈{quantity * price:.2f} {quote}); {base} before: {base_before}")

    buy_id = smoke_client_order_id()
    buy = await gateway.place_market_order(symbol, "BUY", quantity, buy_id)
    print(describe("buy", buy))
    if not (buy.is_final and buy.has_fill):
        raise RuntimeError("buy did not fill; nothing to close")
    readback = await gateway.get_order_by_client_id(symbol, buy_id)
    print(describe("buy read-back", readback))

    held = buy.filled_quantity - (buy.fee_cost if buy.fee_currency == base else 0.0)
    sell_quantity = rules.limit_quantity(held, price)
    if not rules.is_tradable(sell_quantity, price):
        print(f"bought {held} {base} cannot be sold (below minimum): left as dust")
        return
    sell_id = smoke_client_order_id()
    sell = await gateway.place_market_order(symbol, "SELL", sell_quantity, sell_id)
    print(describe("sell", sell))
    readback = await gateway.get_order_by_client_id(symbol, sell_id)
    print(describe("sell read-back", readback))
    print(f"{base} after: {await gateway.get_balance(base)} (before {base_before}); "
          f"{quote} after: {await gateway.get_balance(quote)}")


async def run(symbol: str) -> None:
    refuse_unless_testnet_mode()
    api_key, api_secret = read_keys()
    gateway = BybitGateway(api_key, api_secret, is_testnet=True,
                           tradable_symbols=settings.tradable_symbols)
    try:
        await check_account(gateway, [symbol], capital=None)
        await smoke(gateway, symbol)
    finally:
        await gateway.close()


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--symbol", required=True)
    parser.add_argument("--confirm-testnet", action="store_true", required=True)
    args = parser.parse_args()
    try:
        asyncio.run(run(args.symbol))
    except Refused as e:
        print(f"Refusing: {e}", file=sys.stderr)
        return 2
    except Exception as e:  # noqa: BLE001
        print(f"Smoke test failed: {type(e).__name__}: {e}", file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    sys.exit(main())
