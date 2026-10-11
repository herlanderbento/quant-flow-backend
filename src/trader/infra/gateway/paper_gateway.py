import itertools
from datetime import datetime, timezone

from shared.domain.exceptions import GatewayException, OrderRejectedException
from trader.domain.interface.exchange_gateway_interface import (
    ORDER_STATUS_CLOSED,
    IExchangeGateway,
    OrderResult,
    TradingRules,
)
from trader.domain.interface.strategy_interface import MarketData
from trader.infra.db.ledger_audit import SimulatedFill
from trader.infra.gateway.bybit_gateway import DEFAULT_TRADABLE_SYMBOLS, BybitGateway

_paper_order_sequence = itertools.count(1)


class PaperExchangeGateway(IExchangeGateway):
    """
    Simulated execution on top of real (public) market data.

    Never sends orders anywhere: fills are computed locally from the current
    best bid/ask plus slippage, and charged a taker fee the way Bybit spot does
    (in the base asset on buys, in the quote asset on sells).
    """

    def __init__(
        self,
        market_data: BybitGateway,
        taker_fee_rate: float,
        slippage_bps: float,
    ):
        if taker_fee_rate < 0 or slippage_bps < 0:
            raise ValueError("Paper fee and slippage must be non-negative.")
        self.market_data = market_data
        self.taker_fee_rate = taker_fee_rate
        self.slippage_rate = slippage_bps / 10_000
        self._orders: dict[str, OrderResult] = {}
        self._filled_at: dict[str, datetime] = {}

    @classmethod
    def with_public_market_data(
        cls, taker_fee_rate: float, slippage_bps: float,
        tradable_symbols: frozenset[str] = DEFAULT_TRADABLE_SYMBOLS,
    ) -> "PaperExchangeGateway":
        # No API keys on purpose: private endpoints cannot be used even by mistake.
        market_data = BybitGateway(api_key="", api_secret="", is_testnet=False,
                                   tradable_symbols=tradable_symbols)
        return cls(market_data, taker_fee_rate, slippage_bps)

    async def get_current_price(self, symbol: str) -> float:
        return await self.market_data.get_current_price(symbol)

    async def get_market_snapshot(self, symbol: str, rsi_period: int = 14) -> MarketData:
        return await self.market_data.get_market_snapshot(symbol, rsi_period)

    async def get_trading_rules(self, symbol: str) -> TradingRules:
        # Same lot sizes and minimums as the real exchange.
        return await self.market_data.get_trading_rules(symbol)

    async def get_balance(self, asset: str) -> float | None:
        # Paper positions exist only in the database; there is no account to reconcile.
        return None

    async def place_market_order(
        self, symbol: str, side: str, quantity: float, client_order_id: str
    ) -> OrderResult:
        side = side.upper()
        if side not in ("BUY", "SELL"):
            raise OrderRejectedException(f"Invalid side '{side}'.")
        if quantity <= 0:
            raise OrderRejectedException("Quantity must be greater than zero.")
        rules = await self.get_trading_rules(symbol)
        if rules.floor_quantity(quantity) != quantity:
            raise OrderRejectedException(f"Quantity {quantity} is not a multiple of the lot step.")

        existing = self._orders.get(client_order_id)
        if existing is not None:
            return existing  # idempotent like an exchange-side orderLinkId

        try:
            bid, ask = await self.market_data.get_best_bid_ask(symbol)
        except GatewayException as e:
            raise OrderRejectedException(f"Paper order not filled, no quote: {e}")

        if not rules.is_tradable(quantity, (bid + ask) / 2):
            raise OrderRejectedException(f"Order {quantity} {symbol} is below the exchange minimum.")

        base, quote = symbol.split("/", 1)
        if side == "BUY":
            price = ask * (1 + self.slippage_rate)
            fee_cost, fee_currency = quantity * self.taker_fee_rate, base
        else:
            price = bid * (1 - self.slippage_rate)
            fee_cost, fee_currency = quantity * price * self.taker_fee_rate, quote

        result = OrderResult(
            order_id=f"paper-{next(_paper_order_sequence)}",
            client_order_id=client_order_id,
            symbol=symbol,
            side=side,
            status=ORDER_STATUS_CLOSED,
            requested_quantity=quantity,
            filled_quantity=quantity,
            average_price=price,
            fee_cost=fee_cost,
            fee_currency=fee_currency,
        )
        self._orders[client_order_id] = result
        self._filled_at[client_order_id] = datetime.now(timezone.utc)
        return result

    def simulated_fills(self) -> list[SimulatedFill]:
        return [
            SimulatedFill(
                client_order_id=cid,
                side=order.side,
                filled_quantity=order.filled_quantity,
                average_price=order.average_price,
                filled_at=self._filled_at[cid],
            )
            for cid, order in self._orders.items()
        ]

    async def get_order_by_client_id(
        self, symbol: str, client_order_id: str
    ) -> OrderResult | None:
        # Simulated fills live only in this process; after a restart an
        # uncommitted paper order is treated as never executed.
        return self._orders.get(client_order_id)

    async def fetch_ohlcv_history(
        self, symbol: str, timeframe: str, since_ms: int, until_ms: int
    ) -> list[list]:
        return await self.market_data.fetch_ohlcv_history(symbol, timeframe, since_ms, until_ms)

    async def close(self) -> None:
        await self.market_data.close()
