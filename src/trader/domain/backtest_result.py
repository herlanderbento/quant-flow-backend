from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Annotated

from pydantic import Strict

from shared.domain.entity import AggregateRoot
from shared.domain.exceptions import EntityValidationException
from shared.domain.value_objects import Uuid
from trader.domain.bot import BotId


@dataclass
class BacktestCreateCommand:
    bot_id: BotId
    strategy_type: str
    symbol: str
    period_start: datetime
    period_end: datetime
    total_return_pct: float | None
    sharpe_ratio: float | None
    max_drawdown_pct: float | None
    win_rate: float | None
    total_trades: int | None
    timeframe: str | None = None
    profit_factor: float | None = None
    expectancy_pct: float | None = None
    buy_and_hold_return_pct: float | None = None
    exposure_pct: float | None = None
    fees_paid: float | None = None
    taker_fee_rate: float | None = None
    slippage_bps: float | None = None


class BacktestResultId(Uuid):
    pass


@dataclass(slots=True, kw_only=True)
class BacktestResult(AggregateRoot):
    id: BacktestResultId = field(default_factory=BacktestResultId)
    bot_id: BotId
    strategy_type: str
    symbol: str
    period_start: datetime
    period_end: datetime
    total_return_pct: Annotated[float | None, Strict()] = None
    sharpe_ratio: Annotated[float | None, Strict()] = None
    max_drawdown_pct: Annotated[float | None, Strict()] = None
    win_rate: Annotated[float | None, Strict()] = None
    total_trades: Annotated[int | None, Strict()] = None
    timeframe: str | None = None
    profit_factor: float | None = None
    expectancy_pct: float | None = None
    buy_and_hold_return_pct: float | None = None
    exposure_pct: float | None = None
    fees_paid: float | None = None
    taker_fee_rate: float | None = None
    slippage_bps: float | None = None
    created_at: Annotated[datetime, Strict()] = field(
        default_factory=lambda: datetime.now(timezone.utc)
    )

    @staticmethod
    def create(command: BacktestCreateCommand) -> "BacktestResult":
        result = BacktestResult(
            bot_id=command.bot_id,
            strategy_type=command.strategy_type,
            symbol=command.symbol,
            period_start=command.period_start,
            period_end=command.period_end,
            total_return_pct=command.total_return_pct,
            sharpe_ratio=command.sharpe_ratio,
            max_drawdown_pct=command.max_drawdown_pct,
            win_rate=command.win_rate,
            total_trades=command.total_trades,
            timeframe=command.timeframe,
            profit_factor=command.profit_factor,
            expectancy_pct=command.expectancy_pct,
            buy_and_hold_return_pct=command.buy_and_hold_return_pct,
            exposure_pct=command.exposure_pct,
            fees_paid=command.fees_paid,
            taker_fee_rate=command.taker_fee_rate,
            slippage_bps=command.slippage_bps,
        )
        result.validate()
        return result

    @property
    def entity_id(self) -> BacktestResultId:
        return self.id

    def validate(self) -> None:
        if self.period_end <= self.period_start:
            raise EntityValidationException(
                "period_end must be after period_start."
            )
        self._validate(
            {
                "id": self.id,
                "bot_id": self.bot_id,
                "strategy_type": self.strategy_type,
                "symbol": self.symbol,
                "period_start": self.period_start,
                "period_end": self.period_end,
                "created_at": self.created_at,
            }
        )
