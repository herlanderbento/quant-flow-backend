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
        )
