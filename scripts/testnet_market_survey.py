"""Read-only: testnet USDT balance and whether the spot market list contains stock-like pairs.

    qft --profile tools run --rm -T testnet_tools python - < scripts/testnet_market_survey.py
"""
import asyncio
import os
from collections import Counter

from trader.infra.gateway.bybit_gateway import TESTNET_HOST, BybitGateway

STOCK_HINTS = ("xstockMultiplier", "symbolType", "marketRegion", "underlyingTicker", "fullName")


async def main() -> None:
    gateway = BybitGateway(os.environ["BYBIT_TESTNET_API_KEY"], os.environ["BYBIT_TESTNET_API_SECRET"],
                           is_testnet=True)
    try:
        assert gateway.api_hosts() == {TESTNET_HOST}
        for asset in ("USDT", "BTC", "ETH"):
            print(f"balance {asset}: {await gateway.get_balance(asset)}")
        markets = await gateway.exchange.load_markets()
        spot = [m for m in markets.values() if m.get("spot")]
        print(f"spot markets loaded: {len(spot)}; non-spot loaded: {len(markets) - len(spot)}")
        for symbol in ("BTC/USDT", "ETH/USDT"):
            info = markets[symbol]["info"]
            print(f"{symbol} info hints: { {k: info.get(k) for k in STOCK_HINTS if k in info} }")
        flagged = [m for m in spot
                   if (m["info"].get("xstockMultiplier") not in (None, "", "0"))
                   or (m["info"].get("symbolType") not in (None, "", "crypto"))]
        print(f"spot pairs with stock hints: {len(flagged)}")
        print("symbolType values:", Counter(m["info"].get("symbolType") for m in spot))
        for m in flagged[:8]:
            print("  ", m["symbol"], {k: m["info"].get(k) for k in STOCK_HINTS if m["info"].get(k)})
    finally:
        await gateway.close()


asyncio.run(main())
