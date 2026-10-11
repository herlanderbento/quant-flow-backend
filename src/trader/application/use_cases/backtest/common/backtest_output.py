from dataclasses import dataclass
import datetime

from trader.domain.backtest_result import BacktestResult


@dataclass(frozen=True)
class BacktestOutput:
    id: str
    bot_id: str
    strategy_type: str
    symbol: str
    period_start: datetime.datetime
    period_end: datetime.datetime
    total_return_pct: float | None
    sharpe_ratio: float | None
    max_drawdown_pct: float | None
    win_rate: float | None
    total_trades: int | None
    created_at: datetime.datetime
    timeframe: str | None = None
    profit_factor: float | None = None
    expectancy_pct: float | None = None
    buy_and_hold_return_pct: float | None = None
    exposure_pct: float | None = None
    fees_paid: float | None = None
    taker_fee_rate: float | None = None
    slippage_bps: float | None = None

    @classmethod
    def from_entity(cls, result: BacktestResult) -> "BacktestOutput":
        return cls(
            id=str(result.id.value),
            bot_id=str(result.bot_id.value),
            strategy_type=result.strategy_type,
            symbol=result.symbol,
            period_start=result.period_start,
            period_end=result.period_end,
            total_return_pct=result.total_return_pct,
            sharpe_ratio=result.sharpe_ratio,
            max_drawdown_pct=result.max_drawdown_pct,
            win_rate=result.win_rate,
            total_trades=result.total_trades,
            created_at=result.created_at,
            timeframe=result.timeframe,
            profit_factor=result.profit_factor,
            expectancy_pct=result.expectancy_pct,
            buy_and_hold_return_pct=result.buy_and_hold_return_pct,
            exposure_pct=result.exposure_pct,
            fees_paid=result.fees_paid,
            taker_fee_rate=result.taker_fee_rate,
            slippage_bps=result.slippage_bps,
        )
