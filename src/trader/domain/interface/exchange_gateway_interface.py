from abc import ABC, abstractmethod
from dataclasses import dataclass
from decimal import ROUND_DOWN, Decimal

from trader.domain.interface.strategy_interface import MarketData

ORDER_STATUS_OPEN = "open"
ORDER_STATUS_CLOSED = "closed"
ORDER_STATUS_CANCELED = "canceled"
ORDER_STATUS_REJECTED = "rejected"
FINAL_ORDER_STATUSES = frozenset(
    {ORDER_STATUS_CLOSED, ORDER_STATUS_CANCELED, ORDER_STATUS_REJECTED}
)


@dataclass(frozen=True)
class TradingRules:
    amount_step: float | None
    min_amount: float | None
    min_cost: float | None
    max_amount: float | None = None
    max_cost: float | None = None

    def floor_quantity(self, quantity: float) -> float:
        if not self.amount_step:
            return quantity
        step = Decimal(str(self.amount_step))
        steps = (Decimal(str(quantity)) / step).to_integral_value(rounding=ROUND_DOWN)
        return float(steps * step)

    def limit_quantity(self, quantity: float, price: float) -> float:
        """Largest quantity <= `quantity` that respects the step and the per-order maximums."""
        if self.max_amount:
            quantity = min(quantity, self.max_amount)
        if self.max_cost and price > 0:
            quantity = min(quantity, self.max_cost / price)
        return self.floor_quantity(quantity)

    def is_tradable(self, quantity: float, price: float) -> bool:
        if quantity <= 0:
            return False
        if self.min_amount and quantity < self.min_amount:
            return False
        if self.min_cost and quantity * price < self.min_cost:
            return False
        return True


@dataclass(frozen=True)
class OrderResult:
    order_id: str
    client_order_id: str | None
    symbol: str
    side: str  # 'BUY' or 'SELL'
    status: str  # one of the ORDER_STATUS_* values
    requested_quantity: float | None
    filled_quantity: float
    average_price: float | None
    fee_cost: float
    fee_currency: str | None

    @property
    def is_final(self) -> bool:
        return self.status in FINAL_ORDER_STATUSES

    @property
    def has_fill(self) -> bool:
        return (
            self.filled_quantity > 0
            and self.average_price is not None
            and self.average_price > 0
        )

    def net_base_quantity(self, base_asset: str) -> float:
        """Base quantity actually received/given up after fees charged in the base asset."""
        if self.fee_currency == base_asset and self.side == "BUY":
            return max(self.filled_quantity - self.fee_cost, 0.0)
        return self.filled_quantity

    def fee_in_quote(self, base_asset: str, quote_asset: str) -> float | None:
        """Fee in quote currency, or None when it was charged in a third currency."""
        if not self.fee_cost or self.fee_currency is None:
            return 0.0
        if self.fee_currency == quote_asset:
            return self.fee_cost
        if self.fee_currency == base_asset and self.average_price:
            return self.fee_cost * self.average_price
        return None


class IExchangeGateway(ABC):
    @abstractmethod
    async def get_current_price(self, symbol: str) -> float:
        """Returns the current price of a trading pair (e.g. BTC/USDT)."""
        pass

    @abstractmethod
    async def get_market_snapshot(self, symbol: str, rsi_period: int = 14) -> MarketData:
        """Returns price and indicators for strategy analysis."""
        pass

    @abstractmethod
    async def get_trading_rules(self, symbol: str) -> TradingRules:
        """Lot step and minimum order size/notional for the symbol."""
        pass

    @abstractmethod
    async def get_balance(self, asset: str) -> float | None:
        """Free balance of an asset (e.g. USDT); None when the gateway has no real account."""
        pass

    @abstractmethod
    async def place_market_order(
        self, symbol: str, side: str, quantity: float, client_order_id: str
    ) -> OrderResult:
        """
        Places a market order tagged with client_order_id and returns its execution state.
        Raises OrderRejectedException when nothing was executed, and
        OrderStateUnknownException when the outcome must be reconciled later.
        """
        pass

    @abstractmethod
    async def get_order_by_client_id(
        self, symbol: str, client_order_id: str
    ) -> OrderResult | None:
        """Looks up an order by client id; None when the exchange has no such order."""
        pass

    @abstractmethod
    async def fetch_ohlcv_history(
        self,
        symbol: str,
        timeframe: str,
        since_ms: int,
        until_ms: int,
    ) -> list[list]:
        """Returns historical OHLCV candles for the given period."""
        pass

    @abstractmethod
    async def close(self) -> None:
        """Closes the async HTTP session."""
        pass
