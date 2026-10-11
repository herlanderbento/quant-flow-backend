import asyncio
import ssl
import time
from datetime import datetime, timezone
from typing import Callable

import aiohttp
import ccxt.async_support as ccxt
from ccxt.base.errors import (
    BadRequest,
    ExchangeError,
    InsufficientFunds,
    InvalidOrder,
    NetworkError,
)

from shared.domain.exceptions import (
    GatewayException,
    OrderRejectedException,
    OrderStateUnknownException,
    UnsafeCredentialException,
)
from trader.domain.interface.exchange_gateway_interface import (
    IExchangeGateway,
    OrderResult,
    TradingRules,
)
from trader.domain.interface.strategy_interface import (
    LIVE_TIMEFRAME,
    SNAPSHOT_CANDLES,
    MarketData,
)
from trader.infra.gateway.indicators import calculate_rsi

# API key permission policy (see verify_api_key_permissions).
REQUIRED_PERMISSION = ("Spot", "SpotTrade")
UTA_BUNDLED_TRADING_PERMISSIONS = frozenset({("Derivatives", "DerivativesTrade")})
# Explicit list of symbols QuantFlow may trade (orders and trading rules). Bybit's own
# classification is not trusted on its own (the testnet tags ZEC/USDT as "xstocks").
DEFAULT_TRADABLE_SYMBOLS = frozenset({"BTC/USDT", "ETH/USDT"})
# Spot instrument allow-list by Bybit `symbolType`: "" is a standard crypto pair.
# Seen on the testnet (2026-10-10): "", "adventure", "xstocks", "mstocks"; unknown -> refused.
ALLOWED_SPOT_SYMBOL_TYPES = frozenset({""})
SENSITIVE_PERMISSION_GROUPS = frozenset({
    "Wallet",             # AccountTransfer, SubMemberTransfer(List), Withdraw
    "FiatP2P", "FiatBitPay", "FiatConvertBroker", "FiatGlobalPay", "BitCard",
    "Earn", "Exchange",   # moves funds into earn products / converts assets
    "Affiliate",
})

MAINNET_HOST = "api.bybit.com"
TESTNET_HOST = "api-testnet.bybit.com"
ORDER_POLL_ATTEMPTS = 5
ORDER_POLL_DELAY_SECONDS = 0.5
# A closed candle older than this many periods means the feed is stale.
MAX_CANDLE_STALENESS_PERIODS = 2


def _now_ms() -> int:
    return int(time.time() * 1000)


class _BybitClient(ccxt.bybit):
    """
    ccxt Bybit client whose HTTP session resolves DNS with the operating system.
    aiohttp otherwise uses aiodns/c-ares when installed, which fails on some
    Windows setups ("Could not contact DNS servers").
    """

    def open(self):
        if self.own_session and self.session is None:
            if self.asyncio_loop is None:
                self.asyncio_loop = asyncio.get_running_loop()
                self.throttler.loop = self.asyncio_loop
            if self.ssl_context is None:
                self.ssl_context = (
                    ssl.create_default_context(cafile=self.cafile) if self.verify else self.verify
                )
            self.tcp_connector = aiohttp.TCPConnector(
                ssl=self.ssl_context,
                enable_cleanup_closed=True,
                resolver=aiohttp.ThreadedResolver(),
            )
            self.session = aiohttp.ClientSession(
                connector=self.tcp_connector, trust_env=self.aiohttp_trust_env
            )
        super().open()


class BybitGateway(IExchangeGateway):
    def __init__(
        self,
        api_key: str,
        api_secret: str,
        is_testnet: bool = False,
        exchange=None,
        order_poll_delay_seconds: float = ORDER_POLL_DELAY_SECONDS,
        clock_ms: Callable[[], int] = _now_ms,
        tradable_symbols: frozenset[str] = DEFAULT_TRADABLE_SYMBOLS,
    ):
        """
        Initializes the Bybit connection.
        Note: receives decrypted keys from the use case.
        `exchange` lets tests inject a fake ccxt client.
        """
        self.order_poll_delay_seconds = order_poll_delay_seconds
        self.tradable_symbols = frozenset(tradable_symbols)
        self.clock_ms = clock_ms
        if exchange is not None:
            self.exchange = exchange
            return

        self.exchange = _BybitClient({
            'apiKey': api_key,
            'secret': api_secret,
            'enableRateLimit': True,
            'options': {
                'defaultType': 'spot',
                # Spot only: fewer requests and no dependency on derivatives/options endpoints.
                'fetchMarkets': {'types': ['spot']},
            }
        })

        if is_testnet:
            self.exchange.set_sandbox_mode(True)
        expected = TESTNET_HOST if is_testnet else MAINNET_HOST
        if self.api_hosts() != {expected}:
            # Never let a testnet gateway reach production (or the reverse) through a
            # library default or option changing underneath us.
            raise UnsafeCredentialException(
                f"Bybit endpoint mismatch: expected {expected}, resolved {sorted(self.api_hosts())}."
            )

    def api_hosts(self) -> set[str]:
        """Every host the client can send private or public requests to."""
        hostname = getattr(self.exchange, "hostname", None) or "bybit.com"
        hosts = set()
        for url in (self.exchange.urls.get("api") or {}).values():
            host = str(url).replace("{hostname}", hostname).split("://", 1)[-1].split("/", 1)[0]
            hosts.add(host)
        return hosts

    async def _ensure_symbol_exists(self, symbol: str) -> None:
        await self.exchange.load_markets()
        if symbol not in self.exchange.markets:
            raise GatewayException(f"Symbol '{symbol}' is not available on Bybit.")
        market = self.exchange.markets[symbol]
        symbol_type = str((market.get('info') or {}).get('symbolType') or '')
        if not market.get('spot') or symbol_type not in ALLOWED_SPOT_SYMBOL_TYPES:
            # Bybit lists tokenised stocks (xstocks/mstocks) and innovation-zone tokens
            # among spot pairs; QuantFlow trades standard crypto spot pairs only.
            raise GatewayException(
                f"Symbol '{symbol}' is not a standard crypto spot pair "
                f"(spot={market.get('spot')}, symbolType='{symbol_type}'); refused."
            )

    async def _ensure_tradable(self, symbol: str) -> None:
        """Before any order or sizing: the symbol must be on QuantFlow's explicit list
        *and* be a standard crypto spot pair for Bybit. Reconciliation is never blocked."""
        if symbol not in self.tradable_symbols:
            raise GatewayException(
                f"Symbol '{symbol}' is not in the tradable list {sorted(self.tradable_symbols)}."
            )
        await self._ensure_symbol_exists(symbol)

    async def get_current_price(self, symbol: str) -> float:
        try:
            await self._ensure_symbol_exists(symbol)
            ticker = await self.exchange.fetch_ticker(symbol)
            price = float(ticker['last'])
            if price <= 0:
                raise GatewayException(f"Invalid price for {symbol}: {price}")
            return price
        except GatewayException:
            raise
        except Exception as e:
            raise GatewayException(f"Error fetching price for {symbol} on Bybit: {str(e)}")

    async def get_best_bid_ask(self, symbol: str) -> tuple[float, float]:
        try:
            await self._ensure_symbol_exists(symbol)
            ticker = await self.exchange.fetch_ticker(symbol)
            bid, ask = ticker.get('bid'), ticker.get('ask')
            if not bid or not ask or bid <= 0 or ask <= 0 or bid > ask:
                raise GatewayException(f"Invalid bid/ask for {symbol}: {bid}/{ask}")
            return float(bid), float(ask)
        except GatewayException:
            raise
        except Exception as e:
            raise GatewayException(f"Error fetching bid/ask for {symbol} on Bybit: {str(e)}")

    async def get_market_snapshot(
        self, symbol: str, rsi_period: int = 14, timeframe: str = LIVE_TIMEFRAME
    ) -> MarketData:
        try:
            await self._ensure_symbol_exists(symbol)
            price = await self.get_current_price(symbol)
            rsi_window = rsi_period + 51
            ohlcv = await self.exchange.fetch_ohlcv(
                symbol, timeframe=timeframe, limit=max(rsi_window, SNAPSHOT_CANDLES) + 1
            )
            period_ms = self.exchange.parse_timeframe(timeframe) * 1000
            now_ms = self.clock_ms()
            # The exchange returns the still-forming candle last: never decide on it.
            closed = [c for c in ohlcv if int(c[0]) + period_ms <= now_ms]
            if not closed:
                raise GatewayException(f"No closed {timeframe} candles for {symbol}.")

            last_close_ms = int(closed[-1][0]) + period_ms
            if now_ms - last_close_ms > MAX_CANDLE_STALENESS_PERIODS * period_ms:
                raise GatewayException(
                    f"Stale market data for {symbol}: last closed candle at {last_close_ms}."
                )

            # RSI on the same window length as the backtest, whatever the fetch size.
            closes = [float(candle[4]) for candle in closed[-rsi_window:]]
            rsi = calculate_rsi(closes, rsi_period)
            indicators = {"rsi": rsi} if rsi is not None else {}
            return MarketData(
                symbol=symbol,
                current_price=price,
                indicators=indicators,
                candle_closed_at=datetime.fromtimestamp(last_close_ms / 1000, tz=timezone.utc),
                candles=[[float(v) for v in candle[:6]] for candle in closed[-SNAPSHOT_CANDLES:]],
            )
        except GatewayException:
            raise
        except Exception as e:
            raise GatewayException(
                f"Error fetching market snapshot for {symbol} on Bybit: {str(e)}"
            )

    async def verify_api_key_permissions(self) -> list[tuple[str, str]]:
        """
        Allow-list policy for the key's permissions (same on testnet and live).
        https://bybit-exchange.github.io/docs/v5/user/apikey-info

        Required: Spot/SpotTrade, read-write, Unified Trading Account.
        Tolerated only on a UTA: Derivatives/DerivativesTrade, documented by Bybit as the
        "Permission of Unified account" and bundled with it by the key UI. It grants nothing
        to QuantFlow: the client loads spot markets only, so no derivative can be ordered.
        Everything else is refused: wallet/fund movements, payments, earn, convert,
        affiliate, other trading products, and any group or value Bybit does not document.
        """
        try:
            response = await self.exchange.privateGetV5UserQueryApi()
            info = response.get('result') or {}
        except Exception as e:
            raise UnsafeCredentialException(f"Could not verify API key permissions: {e}")

        permissions = info.get('permissions') or {}
        granted = {
            (group, value)
            for group, values in permissions.items()
            for value in (values or [])
        }
        sensitive = sorted(p for p in granted if p[0] in SENSITIVE_PERMISSION_GROUPS)
        if sensitive:
            raise UnsafeCredentialException(
                f"API key can move funds or act outside trading {sensitive}; create a key "
                "without wallet, transfer, withdrawal, payment, earn or convert permissions."
            )
        if str(info.get('readOnly')) == '1':
            raise UnsafeCredentialException("API key is read-only and cannot place orders.")
        if REQUIRED_PERMISSION not in granted:
            raise UnsafeCredentialException("API key lacks the Spot 'SpotTrade' permission.")
        # Spot market BUY quantities are only in base coin on a Unified Trading Account;
        # a classic account would read the same number as quote currency to spend.
        if str(info.get('uta')) != '1':
            raise UnsafeCredentialException(
                "Account is not a Unified Trading Account (uta != 1); market order "
                "quantities would be misinterpreted."
            )
        not_allowed = sorted(granted - {REQUIRED_PERMISSION} - UTA_BUNDLED_TRADING_PERMISSIONS)
        if not_allowed:
            raise UnsafeCredentialException(
                f"API key has permissions outside the allow-list {not_allowed} "
                "(other trading products or undocumented permissions); "
                "create a key with Spot -> Trade only."
            )
        return sorted(granted)

    async def get_balance(self, asset: str) -> float | None:
        try:
            balance = await self.exchange.fetch_balance()
            if asset in balance and isinstance(balance[asset], dict):
                return float(balance[asset].get('free') or 0.0)
            return 0.0
        except Exception as e:
            raise GatewayException(f"Error fetching balance for {asset} on Bybit: {str(e)}")

    async def get_trading_rules(self, symbol: str) -> TradingRules:
        try:
            await self._ensure_tradable(symbol)
            market = self.exchange.market(symbol)
            limits = market.get('limits') or {}
            lot = (market.get('info') or {}).get('lotSizeFilter') or {}
            return TradingRules(
                amount_step=_to_float((market.get('precision') or {}).get('amount')),
                min_amount=_to_float((limits.get('amount') or {}).get('min')),
                min_cost=_to_float((limits.get('cost') or {}).get('min')),
                # Market orders have their own (lower) cap on Bybit spot when published.
                max_amount=_to_float(lot.get('maxMarketOrderQty'))
                or _to_float((limits.get('amount') or {}).get('max')),
                max_cost=_to_float((limits.get('cost') or {}).get('max')),
            )
        except GatewayException:
            raise
        except Exception as e:
            raise GatewayException(f"Error loading trading rules for {symbol}: {str(e)}")

    async def place_market_order(
        self, symbol: str, side: str, quantity: float, client_order_id: str
    ) -> OrderResult:
        try:
            await self._ensure_tradable(symbol)
            quantity = float(self.exchange.amount_to_precision(symbol, quantity))
        except GatewayException:
            raise
        except Exception as e:
            # Nothing was sent: a quantity below the lot step is a definitive refusal.
            raise OrderRejectedException(f"Invalid quantity {quantity} for {symbol}: {e}")
        if quantity <= 0:
            raise OrderRejectedException(f"Quantity rounds to zero for {symbol}.")

        try:
            created = await self.exchange.create_order(
                symbol,
                'market',
                side.lower(),
                quantity,
                None,
                # Explicit: the quantity is in base coin for buys and sells alike.
                {'clientOrderId': client_order_id, 'marketUnit': 'baseCoin'},
            )
        except InsufficientFunds as e:
            raise OrderRejectedException(
                f"Insufficient balance on Bybit to execute {side} of {quantity} {symbol}: {e}"
            )
        except (InvalidOrder, BadRequest) as e:
            raise OrderRejectedException(f"Bybit rejected {side} {quantity} {symbol}: {e}")
        except NetworkError as e:
            # Includes RequestTimeout: the order may have reached the exchange.
            raise OrderStateUnknownException(
                f"No confirmation for order {client_order_id} on {symbol}: {e}"
            )
        except ExchangeError as e:
            raise OrderStateUnknownException(
                f"Exchange error placing order {client_order_id} on {symbol}: {e}"
            )

        # Bybit v5 create-order responses only contain ids: read back the real execution.
        last_seen: OrderResult | None = None
        for attempt in range(ORDER_POLL_ATTEMPTS):
            try:
                last_seen = await self.get_order_by_client_id(symbol, client_order_id)
            except GatewayException:
                last_seen = None
            if last_seen is not None and last_seen.is_final:
                return last_seen
            if attempt < ORDER_POLL_ATTEMPTS - 1:
                await asyncio.sleep(self.order_poll_delay_seconds)

        if last_seen is not None:
            return last_seen
        raise OrderStateUnknownException(
            f"Order {created.get('id')} ({client_order_id}) on {symbol} was sent "
            "but its execution could not be confirmed"
        )

    async def get_order_by_client_id(
        self, symbol: str, client_order_id: str
    ) -> OrderResult | None:
        try:
            await self._ensure_symbol_exists(symbol)
            market = self.exchange.market(symbol)
            request = {
                'category': 'spot',
                'symbol': market['id'],
                'orderLinkId': client_order_id,
            }
            for endpoint in (
                self.exchange.privateGetV5OrderRealtime,
                self.exchange.privateGetV5OrderHistory,
            ):
                response = await endpoint(request)
                rows = (response.get('result') or {}).get('list') or []
                if rows:
                    return _to_order_result(self.exchange.parse_order(rows[0], market))
            return None
        except GatewayException:
            raise
        except Exception as e:
            raise GatewayException(
                f"Error fetching order {client_order_id} on {symbol}: {str(e)}"
            )

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
            limit = 1000  # Bybit kline maximum per request

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
                # The exchange may return fewer rows than `limit` per page (Bybit: 999),
                # so a short page is not the end: stop only when no progress is made.

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


def _to_float(value) -> float | None:
    if value is None or value == "":
        return None
    return float(value)


def _to_order_result(order: dict) -> OrderResult:
    if not order.get('id') or not order.get('side') or not order.get('status'):
        raise GatewayException(f"Incomplete order payload from Bybit: {order.get('id')}")

    fee = order.get('fee') or {}
    return OrderResult(
        order_id=str(order['id']),
        client_order_id=order.get('clientOrderId'),
        symbol=order['symbol'],
        side=order['side'].upper(),
        status=order['status'],
        requested_quantity=_to_float(order.get('amount')),
        filled_quantity=_to_float(order.get('filled')) or 0.0,
        average_price=_to_float(order.get('average')),
        fee_cost=_to_float(fee.get('cost')) or 0.0,
        fee_currency=fee.get('currency'),
    )
