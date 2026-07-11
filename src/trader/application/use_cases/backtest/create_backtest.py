from dataclasses import dataclass
from datetime import datetime, timedelta, timezone

from account.domain.user import UserId
from account.domain.user_repository import IUserRepository
from shared.application.use_cases import UseCase
from shared.domain.exceptions import (
    ForbiddenException,
    InvalidArgumentException,
    NotFoundException,
)
from trader.application.backtest_engine import candle_from_ohlcv, run_backtest
from trader.application.use_cases.backtest.common.backtest_output import BacktestOutput
from trader.domain.backtest_result import BacktestCreateCommand, BacktestResult
from trader.domain.bot import BotId
from trader.domain.repositories.backtest_repository import IBacktestRepository
from trader.domain.repositories.bot_repository import IBotRepository
from trader.domain.strategies.strategy_factory import StrategyFactory
from trader.infra.gateway.bybit_gateway import BybitGateway

MAX_BACKTEST_DAYS = 90
MIN_CANDLES = 20
VALID_TIMEFRAMES = frozenset({"15m", "1h", "4h", "1d"})


@dataclass
class CreateBacktestInput:
    user_id: UserId
    bot_id: BotId
    period_start: datetime
    period_end: datetime
    timeframe: str = "1h"


@dataclass(frozen=True)
class CreateBacktestOutput(BacktestOutput):
    pass


class CreateBacktestUseCase(UseCase):
    def __init__(
        self,
        bot_repository: IBotRepository,
        backtest_repository: IBacktestRepository,
        user_repository: IUserRepository,
    ):
        self.bot_repository = bot_repository
        self.backtest_repository = backtest_repository
        self.user_repository = user_repository

    async def execute(self, input: CreateBacktestInput) -> CreateBacktestOutput:
        if not await self.user_repository.find_by_id(input.user_id.value):
            raise NotFoundException(f"User with id {input.user_id.value} not found")

        bot = await self.bot_repository.find_by_id(input.bot_id)
        if not bot:
            raise NotFoundException(f"Bot with id {input.bot_id} not found")

        if bot.user_id.value != input.user_id.value:
            raise ForbiddenException("You do not have permission to backtest this Bot")

        period_start = _ensure_utc(input.period_start)
        period_end = _ensure_utc(input.period_end)

        if period_end <= period_start:
            raise InvalidArgumentException("period_end must be after period_start")

        if period_end - period_start > timedelta(days=MAX_BACKTEST_DAYS):
            raise InvalidArgumentException(
                f"Backtest period cannot exceed {MAX_BACKTEST_DAYS} days"
            )

        timeframe = input.timeframe.lower()
        if timeframe not in VALID_TIMEFRAMES:
            raise InvalidArgumentException(
                f"timeframe must be one of: {sorted(VALID_TIMEFRAMES)}"
            )

        gateway = BybitGateway(api_key="", api_secret="", is_testnet=False)
        try:
            raw_candles = await gateway.fetch_ohlcv_history(
                bot.symbol,
                timeframe,
                since_ms=int(period_start.timestamp() * 1000),
                until_ms=int(period_end.timestamp() * 1000),
            )
        finally:
            await gateway.close()

        candles = [candle_from_ohlcv(row) for row in raw_candles]
        candles = [c for c in candles if period_start <= c.timestamp <= period_end]

        if len(candles) < MIN_CANDLES:
            raise InvalidArgumentException(
                f"Not enough historical data for backtest (need at least {MIN_CANDLES} candles)"
            )

        strategy = StrategyFactory.get_strategy(bot.strategy_type)
        metrics = await run_backtest(
            candles=candles,
            strategy=strategy,
            symbol=bot.symbol,
            allocated_capital=bot.allocated_capital,
            stop_loss_pct=bot.stop_loss_pct,
            take_profit_pct=bot.take_profit_pct,
        )

        command = BacktestCreateCommand(
            bot_id=bot.id,
            strategy_type=bot.strategy_type,
            symbol=bot.symbol,
            period_start=period_start,
            period_end=period_end,
            total_return_pct=metrics.total_return_pct,
            sharpe_ratio=metrics.sharpe_ratio,
            max_drawdown_pct=metrics.max_drawdown_pct,
            win_rate=metrics.win_rate,
            total_trades=metrics.total_trades,
        )

        entity = BacktestResult.create(command)

        await self.backtest_repository.insert(entity)

        return self.__to_output(entity)

    def __to_output(self, entity: BacktestResult) -> CreateBacktestOutput:
        return CreateBacktestOutput.from_entity(entity)


def _ensure_utc(value: datetime) -> datetime:
    if value.tzinfo is None:
        return value.replace(tzinfo=timezone.utc)
    return value.astimezone(timezone.utc)
