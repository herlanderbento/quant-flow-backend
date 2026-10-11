from datetime import datetime
from uuid import UUID

from pydantic import BaseModel, ConfigDict
from typing import Any

from shared.infra.api.presenter import CollectionPresenter, meta_from_output
from trader.application.use_cases.backtest.common.backtest_output import BacktestOutput


class BacktestPresenter(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: UUID
    bot_id: UUID
    strategy_type: str
    symbol: str
    period_start: datetime
    period_end: datetime
    total_return_pct: float | None
    sharpe_ratio: float | None
    max_drawdown_pct: float | None
    win_rate: float | None
    total_trades: int | None
    created_at: datetime
    timeframe: str | None = None
    profit_factor: float | None = None
    expectancy_pct: float | None = None
    buy_and_hold_return_pct: float | None = None
    exposure_pct: float | None = None
    fees_paid: float | None = None
    taker_fee_rate: float | None = None
    slippage_bps: float | None = None

    @classmethod
    def from_output(cls, output: BacktestOutput) -> "BacktestPresenter":
        return cls(
            id=UUID(output.id),
            bot_id=UUID(output.bot_id),
            strategy_type=output.strategy_type,
            symbol=output.symbol,
            period_start=output.period_start,
            period_end=output.period_end,
            total_return_pct=output.total_return_pct,
            sharpe_ratio=output.sharpe_ratio,
            max_drawdown_pct=output.max_drawdown_pct,
            win_rate=output.win_rate,
            total_trades=output.total_trades,
            created_at=output.created_at,
            timeframe=output.timeframe,
            profit_factor=output.profit_factor,
            expectancy_pct=output.expectancy_pct,
            buy_and_hold_return_pct=output.buy_and_hold_return_pct,
            exposure_pct=output.exposure_pct,
            fees_paid=output.fees_paid,
            taker_fee_rate=output.taker_fee_rate,
            slippage_bps=output.slippage_bps,
        )


class BacktestTradePresenter(BaseModel):
    entry_time: datetime
    exit_time: datetime
    entry_price: float
    exit_price: float
    quantity: float
    cost: float
    pnl: float
    pnl_pct: float
    exit_reason: str


class CreateBacktestPresenter(BacktestPresenter):
    trades: list[BacktestTradePresenter] = []

    @classmethod
    def from_create_output(cls, output: Any) -> "CreateBacktestPresenter":
        base = BacktestPresenter.from_output(output).model_dump()
        return cls(
            **base,
            trades=[BacktestTradePresenter(**trade.__dict__) for trade in output.trades],
        )


class BacktestCollectionPresenter(CollectionPresenter[BacktestPresenter]):
    @classmethod
    def from_output(cls, output: Any) -> "BacktestCollectionPresenter":
        return cls(
            data=[BacktestPresenter.from_output(item) for item in output.items],
            meta=meta_from_output(output),
        )
