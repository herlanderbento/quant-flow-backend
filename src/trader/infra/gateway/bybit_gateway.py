import ccxt.async_support as ccxt
from ccxt.base.errors import ExchangeError, InsufficientFunds

from shared.domain.exceptions import GatewayException
from trader.domain.interface.exchange_gateway_interface import IExchangeGateway, OrderResult
from trader.domain.interface.strategy_interface import MarketData
from trader.infra.gateway.indicators import calculate_rsi


class BybitGateway(IExchangeGateway):
    def __init__(self, api_key: str, api_secret: str, is_testnet: bool = False):
        """
        Initializes the Bybit connection.
        Note: receives decrypted keys from the use case.
        """
        self.exchange = ccxt.bybit({
            'apiKey': api_key,
            'secret': api_secret,
            'enableRateLimit': True,
            'options': {
                'defaultType': 'spot'
            }
        })

        if is_testnet:
            self.exchange.set_sandbox_mode(True)

    async def _ensure_symbol_exists(self, symbol: str) -> None:
        await self.exchange.load_markets()
        if symbol not in self.exchange.markets:
            raise GatewayException(f"Symbol '{symbol}' is not available on Bybit.")

    async def get_current_price(self, symbol: str) -> float:
        try:
            await self._ensure_symbol_exists(symbol)
            ticker = await self.exchange.fetch_ticker(symbol)
            return float(ticker['last'])
        except GatewayException:
            raise
        except Exception as e:
            raise GatewayException(f"Error fetching price for {symbol} on Bybit: {str(e)}")

    async def get_market_snapshot(self, symbol: str, rsi_period: int = 14) -> MarketData:
        try:
            await self._ensure_symbol_exists(symbol)
            price = await self.get_current_price(symbol)
            ohlcv = await self.exchange.fetch_ohlcv(
                symbol, timeframe='1h', limit=rsi_period + 50
            )
            closes = [float(candle[4]) for candle in ohlcv]
            rsi = calculate_rsi(closes, rsi_period)
            indicators = {"rsi": rsi} if rsi is not None else {}
            return MarketData(
                symbol=symbol,
                current_price=price,
                indicators=indicators,
            )
        except GatewayException:
            raise
        except Exception as e:
            raise GatewayException(
                f"Error fetching market snapshot for {symbol} on Bybit: {str(e)}"
            )

    async def get_balance(self, asset: str) -> float:
        try:
            balance = await self.exchange.fetch_balance()
            if asset in balance:
                return float(balance[asset]['free'])
            return 0.0
        except Exception as e:
            raise GatewayException(f"Error fetching balance for {asset} on Bybit: {str(e)}")

    async def place_market_order(self, symbol: str, side: str, quantity: float) -> OrderResult:
        try:
            order = await self.exchange.create_market_order(
                symbol=symbol,
                side=side.lower(),
                amount=quantity
            )

            return OrderResult(
                order_id=str(order['id']),
                symbol=order['symbol'],
                side=order['side'].upper(),
                price=float(order.get('price', order.get('average', 0.0))),
                quantity=float(order['amount']),
                status=order['status']
            )

        except InsufficientFunds:
            raise GatewayException(
                f"Insufficient balance on Bybit to execute {side} of {quantity} {symbol}"
            )
        except ExchangeError as e:
            raise GatewayException(f"Error placing order on Bybit: {str(e)}")
        except Exception as e:
            raise GatewayException(f"Unexpected error in Gateway: {str(e)}")

    async def fetch_ohlcv_history(
        self,
        symbol: str,
        timeframe: str,
        since_ms: int,
        until_ms: int,
    ) -> list[list]:
        try:
            await self._ensure_symbol_exists(symbol)
            all_candles: list[list] = []
            cursor = since_ms
            limit = 200

            while cursor < until_ms:
                batch = await self.exchange.fetch_ohlcv(
                    symbol,
                    timeframe=timeframe,
                    since=cursor,
                    limit=limit,
                )
                if not batch:
                    break

                for candle in batch:
                    ts = int(candle[0])
                    if ts > until_ms:
                        break
                    if ts >= since_ms:
                        all_candles.append(candle)

                last_ts = int(batch[-1][0])
                next_cursor = last_ts + 1
                if next_cursor <= cursor:
                    break
                cursor = next_cursor

                if len(batch) < limit:
                    break

            return all_candles
        except GatewayException:
            raise
        except Exception as e:
            raise GatewayException(
                f"Error fetching OHLCV history for {symbol} on Bybit: {str(e)}"
            )

    async def close(self) -> None:
        """Required to avoid memory leaks in the async worker."""
        await self.exchange.close()
