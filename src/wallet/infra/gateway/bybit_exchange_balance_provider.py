from wallet.application.ports.exchange_balance_provider import (
    AssetBalance,
    IExchangeBalanceProvider,
)
from trader.infra.gateway.bybit_gateway import BybitGateway


class BybitExchangeBalanceProvider(IExchangeBalanceProvider):
    async def fetch_balances(
        self, api_key: str, api_secret: str, is_testnet: bool
    ) -> dict[str, AssetBalance]:
        gateway = BybitGateway(api_key, api_secret, is_testnet=is_testnet)
        try:
            raw_balance = await gateway.exchange.fetch_balance()
            balances: dict[str, AssetBalance] = {}
            for asset, amounts in raw_balance.items():
                if not isinstance(amounts, dict):
                    continue
                free = float(amounts.get("free") or 0)
                locked = float(amounts.get("used") or 0)
                if free > 0 or locked > 0:
                    balances[asset] = AssetBalance(free=free, locked=locked)
            return balances
        finally:
            await gateway.close()

    async def estimate_total_equity_usdt(
        self,
        api_key: str,
        api_secret: str,
        is_testnet: bool,
        balances: dict[str, AssetBalance],
    ) -> float:
        gateway = BybitGateway(api_key, api_secret, is_testnet=is_testnet)
        try:
            total = 0.0
            for asset, balance in balances.items():
                amount = balance.free + balance.locked
                if amount <= 0:
                    continue
                if asset == "USDT":
                    total += amount
                    continue
                symbol = f"{asset}/USDT"
                try:
                    price = await gateway.get_current_price(symbol)
                    total += amount * price
                except Exception:
                    continue
            return total
        finally:
            await gateway.close()
