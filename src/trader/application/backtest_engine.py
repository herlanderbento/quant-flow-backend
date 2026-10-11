from dataclasses import dataclass, field
from datetime import datetime, timedelta, timezone
from math import sqrt

from trader.domain.interface.strategy_interface import (
    IBotStrategy,
    MarketData,
    TradeSignal,
)
from trader.infra.gateway.indicators import calculate_rsi

SECONDS_PER_YEAR = 365 * 24 * 3600  # crypto trades 24/7

# Same number of candles the live snapshot computes indicators from.
def indicator_window(rsi_period: int) -> int:
    return rsi_period + 51


@dataclass(frozen=True)
class OhlcvCandle:
    timestamp: datetime  # candle open time
    open: float
    high: float
    low: float
    close: float
    volume: float


@dataclass(frozen=True)
class BacktestCosts:
    taker_fee_rate: float = 0.001
    slippage_bps: float = 5.0

    @property
    def slippage_rate(self) -> float:
        return self.slippage_bps / 10_000


@dataclass(frozen=True)
class BacktestTrade:
    entry_time: datetime
    exit_time: datetime
    entry_price: float
    exit_price: float
    quantity: float
    cost: float
    pnl: float
    pnl_pct: float
    exit_reason: str


@dataclass(frozen=True)
class BacktestMetrics:
    total_return_pct: float
    max_drawdown_pct: float
    win_rate: float
    total_trades: int
    sharpe_ratio: float | None
    profit_factor: float | None = None
    expectancy_pct: float | None = None
    avg_win_pct: float | None = None
    avg_loss_pct: float | None = None
    buy_and_hold_return_pct: float | None = None
    exposure_pct: float = 0.0
    fees_paid: float = 0.0
    trades: list[BacktestTrade] = field(default_factory=list)


@dataclass
class _Position:
    entry_time: datetime
    entry_price: float
    quantity: float  # net of the base-asset entry fee
    cost: float  # quote spent


async def run_backtest(
    *,
    candles: list[OhlcvCandle],
    strategy: IBotStrategy,
    symbol: str,
    allocated_capital: float,
    stop_loss_pct: float,
    take_profit_pct: float,
    rsi_period: int = 14,
    costs: BacktestCosts = BacktestCosts(),
    trade_start: datetime | None = None,
    timeframe_seconds: int = 3600,
) -> BacktestMetrics:
    """
    Long-only spot simulation mirroring the live worker:
    decisions on closed candles, fills at the next open with slippage and taker fees,
    stop-loss/take-profit checked against each candle's high/low.
    Candles before `trade_start` only warm up indicators.
    """
    allocated_capital = float(allocated_capital)
    stop_loss_pct = float(stop_loss_pct)
    take_profit_pct = float(take_profit_pct)
    if allocated_capital <= 0:
        return BacktestMetrics(0.0, 0.0, 0.0, 0, None)

    fee = costs.taker_fee_rate
    slip = costs.slippage_rate
    window = indicator_window(rsi_period)
    candle_window = int(getattr(strategy, "required_candles", 0) or 0)
    period = timedelta(seconds=timeframe_seconds)
    raw_rows: list[list[float]] = []

    cash = allocated_capital
    position: _Position | None = None
    pending_entry = False
    pending_exit_reason: str | None = None
    trades: list[BacktestTrade] = []
    fees_paid = 0.0
    equity_curve: list[float] = []
    candles_in_market = 0
    trading_candles: list[OhlcvCandle] = []
    closes: list[float] = []

    def close_position(when: datetime, raw_price: float, reason: str) -> None:
        nonlocal cash, position, fees_paid
        price = raw_price * (1 - slip)
        gross = position.quantity * price
        exit_fee = gross * fee
        proceeds = gross - exit_fee
        fees_paid += exit_fee
        pnl = proceeds - position.cost
        trades.append(
            BacktestTrade(
                entry_time=position.entry_time,
                exit_time=when,
                entry_price=position.entry_price,
                exit_price=price,
                quantity=position.quantity,
                cost=position.cost,
                pnl=pnl,
                pnl_pct=pnl / position.cost * 100,
                exit_reason=reason,
            )
        )
        cash = proceeds
        position = None

    for candle in candles:
        closes.append(candle.close)
        if candle_window:
            raw_rows.append([candle.timestamp.timestamp() * 1000, candle.open, candle.high,
                             candle.low, candle.close, candle.volume])
        trading = trade_start is None or candle.timestamp >= trade_start

        if trading:
            trading_candles.append(candle)

            # 1. Orders decided at the previous close execute at this open.
            if pending_exit_reason and position is not None:
                close_position(candle.timestamp, candle.open, pending_exit_reason)
            elif pending_entry and position is None and cash > 0:
                price = candle.open * (1 + slip)
                gross_quantity = cash / price
                entry_fee_base = gross_quantity * fee
                fees_paid += entry_fee_base * price
                position = _Position(
                    entry_time=candle.timestamp,
                    entry_price=price,
                    quantity=gross_quantity - entry_fee_base,
                    cost=cash,
                )
                cash = 0.0
            pending_entry = False
            pending_exit_reason = None

            # 2. Intrabar stop-loss / take-profit; if both are touched, assume the stop.
            if position is not None:
                stop = position.entry_price * (1 - stop_loss_pct / 100)
                target = position.entry_price * (1 + take_profit_pct / 100)
                if candle.low <= stop:
                    close_position(candle.timestamp, min(candle.open, stop), "STOP_LOSS")
                elif candle.high >= target:
                    close_position(candle.timestamp, max(candle.open, target), "TAKE_PROFIT")

        # 3. Decide on the closed candle, with the same indicator window as live.
        rsi = calculate_rsi(closes[-window:], rsi_period)
        market = MarketData(
            symbol=symbol,
            current_price=candle.close,
            indicators={"rsi": rsi} if rsi is not None else {},
            candle_closed_at=candle.timestamp + period,
            candles=raw_rows[-candle_window:] if candle_window else None,
        )

        if not trading:
            continue

        signal = await strategy.analyze(market)
        if position is not None:
            candles_in_market += 1
            if signal == TradeSignal.SELL:
                pending_exit_reason = "SIGNAL"
        elif signal == TradeSignal.BUY:
            pending_entry = True

        equity_curve.append(
            cash + (position.quantity * candle.close if position is not None else 0.0)
        )

    if position is not None and trading_candles:
        last = trading_candles[-1]
        close_position(last.timestamp, last.close, "END_OF_DATA")
        equity_curve[-1] = cash

    final_equity = cash
    return _metrics(
        allocated_capital=allocated_capital,
        final_equity=final_equity,
        equity_curve=equity_curve,
        trades=trades,
        fees_paid=fees_paid,
        candles=trading_candles,
        candles_in_market=candles_in_market,
        costs=costs,
        timeframe_seconds=timeframe_seconds,
    )


def _metrics(
    *,
    allocated_capital: float,
    final_equity: float,
    equity_curve: list[float],
    trades: list[BacktestTrade],
    fees_paid: float,
    candles: list[OhlcvCandle],
    candles_in_market: int,
    costs: BacktestCosts,
    timeframe_seconds: int,
) -> BacktestMetrics:
    total_return_pct = (final_equity - allocated_capital) / allocated_capital * 100

    peak = allocated_capital
    max_drawdown_pct = 0.0
    for equity in equity_curve:
        peak = max(peak, equity)
        max_drawdown_pct = min(max_drawdown_pct, (equity - peak) / peak * 100)

    wins = [t for t in trades if t.pnl > 0]
    losses = [t for t in trades if t.pnl <= 0]
    gross_profit = sum(t.pnl for t in wins)
    gross_loss = -sum(t.pnl for t in losses)

    def mean(values: list[float]) -> float | None:
        return sum(values) / len(values) if values else None

    return BacktestMetrics(
        total_return_pct=round(total_return_pct, 4),
        max_drawdown_pct=round(max_drawdown_pct, 4),
        win_rate=round(len(wins) / len(trades), 4) if trades else 0.0,
        total_trades=len(trades),
        sharpe_ratio=_round(_annualized_sharpe([allocated_capital] + equity_curve, timeframe_seconds)),
        profit_factor=_round(gross_profit / gross_loss) if gross_loss > 0 else None,
        expectancy_pct=_round(mean([t.pnl_pct for t in trades])),
        avg_win_pct=_round(mean([t.pnl_pct for t in wins])),
        avg_loss_pct=_round(mean([t.pnl_pct for t in losses])),
        buy_and_hold_return_pct=_round(_buy_and_hold(candles, costs)),
        exposure_pct=round(candles_in_market / len(candles) * 100, 4) if candles else 0.0,
        fees_paid=round(fees_paid, 8),
        trades=trades,
    )


def _round(value: float | None) -> float | None:
    return round(value, 4) if value is not None else None


def _buy_and_hold(candles: list[OhlcvCandle], costs: BacktestCosts) -> float | None:
    """Same costs as the strategy: buy at the first open, sell at the last close."""
    if not candles:
        return None
    entry = candles[0].open * (1 + costs.slippage_rate)
    exit_ = candles[-1].close * (1 - costs.slippage_rate)
    quantity = (1 / entry) * (1 - costs.taker_fee_rate)
    proceeds = quantity * exit_ * (1 - costs.taker_fee_rate)
    return (proceeds - 1) * 100


def _annualized_sharpe(equity_curve: list[float], timeframe_seconds: int) -> float | None:
    returns = [
        (equity_curve[i] - equity_curve[i - 1]) / equity_curve[i - 1]
        for i in range(1, len(equity_curve))
        if equity_curve[i - 1] > 0
    ]
    if len(returns) < 2:
        return None
    mean_return = sum(returns) / len(returns)
    variance = sum((r - mean_return) ** 2 for r in returns) / (len(returns) - 1)
    std_dev = sqrt(variance)
    if std_dev == 0:
        return None
    return mean_return / std_dev * sqrt(SECONDS_PER_YEAR / timeframe_seconds)


def candle_from_ohlcv(row: list) -> OhlcvCandle:
    return OhlcvCandle(
        timestamp=datetime.fromtimestamp(row[0] / 1000, tz=timezone.utc),
        open=float(row[1]),
        high=float(row[2]),
        low=float(row[3]),
        close=float(row[4]),
        volume=float(row[5]),
    )
