"""Read-only: every non-zero balance of the testnet trading (Unified) account, per asset.

    qft --profile tools run --rm -T testnet_tools python - < scripts/testnet_balances.py
"""
import asyncio
import os

from trader.infra.gateway.bybit_gateway import TESTNET_HOST, BybitGateway


async def main() -> None:
    gateway = BybitGateway(os.environ["BYBIT_TESTNET_API_KEY"], os.environ["BYBIT_TESTNET_API_SECRET"],
                           is_testnet=True)
    try:
        assert gateway.api_hosts() == {TESTNET_HOST}
        balance = await gateway.exchange.fetch_balance()  # ccxt: UNIFIED account for a UTA
        account = (balance.get("info") or {}).get("result", {}).get("list", [{}])[0]
        print(f"accountType: {account.get('accountType')}  totalEquity(USD): {account.get('totalEquity')}  "
              f"totalAvailableBalance(USD): {account.get('totalAvailableBalance')}")
        for coin, amounts in sorted((balance.get("total") or {}).items()):
            if amounts:
                print(f"{coin}: free={balance['free'].get(coin)} used={balance['used'].get(coin)} total={amounts}")
        print(f"gateway.get_balance('USDT') -> {await gateway.get_balance('USDT')}")
    finally:
        await gateway.close()


asyncio.run(main())
