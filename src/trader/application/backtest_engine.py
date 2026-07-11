from dataclasses import dataclass
from datetime import datetime, timezone
from math import sqrt

from trader.application.risk_management import evaluate_exit
from trader.domain.interface.strategy_interface import (
    IBotStrategy,
    MarketData,
    TradeSignal,
)
from trader.infra.gateway.indicators import calculate_rsi


@dataclass(frozen=True)
class OhlcvCandle:
    timestamp: datetime
    open: float
    high: float
    low: float
    close: float
    volume: float


@dataclass(frozen=True)
class BacktestMetrics:
    total_return_pct: float
    max_drawdown_pct: float
    win_rate: float
    total_trades: int
    sharpe_ratio: float | None


@dataclass
class _OpenPosition:
    entry_price: float
    quantity: float
    entry_equity: float


async def run_backtest(
    *,
    candles: list[OhlcvCandle],
    strategy: IBotStrategy,
    symbol: str,
    allocated_capital: float,
    stop_loss_pct: float,
    take_profit_pct: float,
    rsi_period: int = 14,
) -> BacktestMetrics:
    if allocated_capital <= 0:
        return BacktestMetrics(0.0, 0.0, 0.0, 0, None)

    equity = float(allocated_capital)
    peak_equity = equity
    max_drawdown_pct = 0.0
    position: _OpenPosition | None = None
    closed_pnls: list[float] = []
    equity_curve: list[float] = [equity]
    closes: list[float] = []

    for candle in candles:
        closes.append(candle.close)
        rsi = calculate_rsi(closes, rsi_period)
        market_data = MarketData(
            symbol=symbol,
            current_price=candle.close,
            indicators={"rsi": rsi} if rsi is not None else {},
        )

        if position is not None:
            decision = evaluate_exit(
                side="BUY",
                entry_price=position.entry_price,
                current_price=candle.close,
                stop_loss_pct=stop_loss_pct,
                take_profit_pct=take_profit_pct,
            )
            signal = await strategy.analyze(market_data)
            should_close = decision.should_exit or signal == TradeSignal.SELL

            if should_close:
                exit_value = position.quantity * candle.close
                pnl = exit_value - position.entry_equity
                equity = position.entry_equity + pnl
                closed_pnls.append(pnl)
                position = None
            else:
                equity = position.quantity * candle.close
        else:
            signal = await strategy.analyze(market_data)
            if signal == TradeSignal.BUY and candle.close > 0:
                quantity = equity / candle.close
                position = _OpenPosition(
                    entry_price=candle.close,
                    quantity=quantity,
                    entry_equity=equity,
                )

        peak_equity = max(peak_equity, equity)
        if peak_equity > 0:
            drawdown = ((equity - peak_equity) / peak_equity) * 100
            max_drawdown_pct = min(max_drawdown_pct, drawdown)
        equity_curve.append(equity)

    if position is not None and candles:
        last_close = candles[-1].close
        exit_value = position.quantity * last_close
        pnl = exit_value - position.entry_equity
        equity = position.entry_equity + pnl
        closed_pnls.append(pnl)
        equity_curve.append(equity)

    total_trades = len(closed_pnls)
    total_return_pct = ((equity - allocated_capital) / allocated_capital) * 100
    wins = sum(1 for pnl in closed_pnls if pnl > 0)
    win_rate = (wins / total_trades) if total_trades > 0 else 0.0
    sharpe_ratio = _calculate_sharpe(equity_curve) if total_trades >= 2 else None

    return BacktestMetrics(
        total_return_pct=round(total_return_pct, 4),
        max_drawdown_pct=round(max_drawdown_pct, 4),
        win_rate=round(win_rate, 4),
        total_trades=total_trades,
        sharpe_ratio=round(sharpe_ratio, 4) if sharpe_ratio is not None else None,
    )


def _calculate_sharpe(equity_curve: list[float]) -> float | None:
    if len(equity_curve) < 3:
        return None

    returns: list[float] = []
    for i in range(1, len(equity_curve)):
        prev = equity_curve[i - 1]
        if prev <= 0:
            continue
        returns.append((equity_curve[i] - prev) / prev)

    if len(returns) < 2:
        return None

    mean_return = sum(returns) / len(returns)
    variance = sum((r - mean_return) ** 2 for r in returns) / (len(returns) - 1)
    std_dev = sqrt(variance)
    if std_dev == 0:
        return None
    return mean_return / std_dev


def candle_from_ohlcv(row: list) -> OhlcvCandle:
    return OhlcvCandle(
        timestamp=datetime.fromtimestamp(row[0] / 1000, tz=timezone.utc),
        open=float(row[1]),
        high=float(row[2]),
        low=float(row[3]),
        close=float(row[4]),
        volume=float(row[5]),
    )
