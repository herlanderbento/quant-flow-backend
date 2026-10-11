"""Read-only: summarise the testnet API key's permissions without printing any identifier.

Run inside the testnet tools container (keys come from its environment):
    qft --profile tools run --rm testnet_tools python scripts/testnet_key_info.py
"""
import asyncio
import os

from trader.infra.gateway.bybit_gateway import TESTNET_HOST, BybitGateway


async def main() -> None:
    gateway = BybitGateway(os.environ["BYBIT_TESTNET_API_KEY"], os.environ["BYBIT_TESTNET_API_SECRET"],
                           is_testnet=True)
    try:
        assert gateway.api_hosts() == {TESTNET_HOST}
        info = (await gateway.exchange.privateGetV5UserQueryApi()).get("result") or {}
        permissions = info.get("permissions") or {}
        print(f"endpoint: {TESTNET_HOST}")
        print(f"uta: {info.get('uta')}  readOnly: {info.get('readOnly')}  "
              f"ip_restricted: {bool(info.get('ips')) and info.get('ips') != ['*']}")
        for group in sorted(permissions):
            if permissions[group]:
                print(f"permission {group}: {permissions[group]}")
    finally:
        await gateway.close()


asyncio.run(main())
