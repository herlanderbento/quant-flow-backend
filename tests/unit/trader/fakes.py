"""Offline exchange doubles shared by unit and integration tests."""
from unittest.mock import AsyncMock

import ccxt.async_support as ccxt

from trader.domain.interface.exchange_gateway_interface import OrderResult, TradingRules
from trader.domain.interface.strategy_interface import (
    IBotStrategy,
    MarketData,
    TradeSignal,
)

SYMBOL = "BTC/USDT"

BTC_USDT_MARKET = {
    "id": "BTCUSDT",
    "symbol": "BTC/USDT",
    "base": "BTC",
    "quote": "USDT",
    "baseId": "BTC",
    "quoteId": "USDT",
    "type": "spot",
    "spot": True,
    "margin": False,
    "swap": False,
    "future": False,
    "option": False,
    "contract": False,
    "linear": None,
    "inverse": None,
    "active": True,
    "precision": {"amount": 0.000001, "price": 0.01},
    "limits": {
        "amount": {"min": 0.000048, "max": 71.0},
        "cost": {"min": 5.0, "max": None},
        "price": {"min": None, "max": None},
    },
    "taker": 0.001,
    "maker": 0.001,
    "info": {},
}


def bybit_order_row(
    *,
    order_id="1001",
    client_order_id="cid-1",
    side="Buy",
    status="Filled",
    qty="0.002",
    filled="0.002",
    avg_price="50000",
    fee=None,
):
    return {
        "orderId": order_id,
        "orderLinkId": client_order_id,
        "symbol": "BTCUSDT",
        "side": side,
        "orderType": "Market",
        "price": "0",
        "qty": qty,
        "avgPrice": avg_price,
        "cumExecQty": filled,
        "cumExecValue": str(float(filled) * float(avg_price or 0)),
        "leavesQty": "0",
        "orderStatus": status,
        "cumFeeDetail": fee if fee is not None else {"BTC": "0.000002"},
        "createdTime": "1700000000000",
        "updatedTime": "1700000000100",
        "marketUnit": "baseCoin",
        "timeInForce": "IOC",
    }


def listing(*rows):
    return {"retCode": 0, "result": {"list": list(rows)}}


def make_fake_bybit():
    exchange = ccxt.bybit({"options": {"defaultType": "spot"}})
    exchange.set_markets([BTC_USDT_MARKET])
    exchange.load_markets = AsyncMock(return_value=exchange.markets)
    exchange.create_order = AsyncMock(
        return_value={"id": "1001", "clientOrderId": None, "info": {"orderId": "1001"}}
    )
    exchange.privateGetV5OrderRealtime = AsyncMock(return_value=listing())
    exchange.privateGetV5OrderHistory = AsyncMock(return_value=listing())
    return exchange


class FixedStrategy(IBotStrategy):
    def __init__(self, signal: TradeSignal):
        self.signal = signal

    @property
    def name(self) -> str:
        return "FIXED"

    async def analyze(self, market_data: MarketData) -> TradeSignal:
        return self.signal


def filled(side, qty, price, client_id, fee_cost=0.0, fee_currency=None, status="closed"):
    return OrderResult(
        order_id=f"ex-{client_id}",
        client_order_id=client_id,
        symbol=SYMBOL,
        side=side,
        status=status,
        requested_quantity=qty,
        filled_quantity=qty,
        average_price=price,
        fee_cost=fee_cost,
        fee_currency=fee_currency,
    )


class ScriptedGateway:
    def __init__(self, price=50000.0):
        self.price = price
        self.sent: list[tuple] = []
        self.on_place = None  # callable(symbol, side, qty, cid) -> OrderResult or raises
        self.lookup: dict[str, OrderResult | None] = {}
        self.lookup_error: Exception | None = None
        self.rules = TradingRules(amount_step=0.000001, min_amount=0.000048, min_cost=5.0)
        self.candle_closed_at = None
        self.balances: dict | None = None  # None behaves like paper (no account)

    async def get_balance(self, asset):
        if self.balances is None:
            return None
        return self.balances.get(asset, 0.0)

    async def get_trading_rules(self, symbol):
        return self.rules

    async def get_market_snapshot(self, symbol, rsi_period=14):
        return MarketData(
            symbol=symbol,
            current_price=self.price,
            indicators={},
            candle_closed_at=self.candle_closed_at,
        )

    async def get_current_price(self, symbol):
        return self.price

    async def place_market_order(self, symbol, side, quantity, client_order_id):
        self.sent.append((side, quantity, client_order_id))
        if self.on_place is None:
            return filled(side, quantity, self.price, client_order_id)
        return self.on_place(symbol, side, quantity, client_order_id)

    async def get_order_by_client_id(self, symbol, client_order_id):
        if self.lookup_error:
            raise self.lookup_error
        return self.lookup.get(client_order_id)
