from dataclasses import dataclass
from datetime import datetime, timezone
from typing import Callable

from trader.domain.bot import Bot
from trader.domain.repositories.trade_repository import ITradeRepository


@dataclass(frozen=True)
class RiskLimits:
    trading_halted: bool = False
    max_daily_loss_pct: float = 3.0
    max_drawdown_pct: float = 10.0
    max_user_exposure: float = 1000.0


@dataclass(frozen=True)
class RiskVerdict:
    allowed: bool
    reason: str | None = None


ALLOWED = RiskVerdict(allowed=True)


class RiskGuard:
    """Account-level limits checked before every new entry. Exits are never blocked."""

    def __init__(
        self,
        trade_repository: ITradeRepository,
        limits: RiskLimits,
        clock: Callable[[], datetime] = lambda: datetime.now(timezone.utc),
    ):
        self.trades = trade_repository
        self.limits = limits
        self.clock = clock

    async def check_entry(self, bot: Bot) -> RiskVerdict:
        if self.limits.trading_halted:
            return RiskVerdict(False, "TRADING_HALTED")

        capital = float(bot.allocated_capital)
        history = await self.trades.realized_pnls(bot.id)

        today = self.clock().date()
        daily_pnl = sum(pnl for closed_at, pnl in history if closed_at.date() == today)
        if daily_pnl <= -capital * self.limits.max_daily_loss_pct / 100:
            return RiskVerdict(False, "MAX_DAILY_LOSS")

        cumulative = peak = 0.0
        for _, pnl in history:
            cumulative += pnl
            peak = max(peak, cumulative)
        if peak - cumulative >= capital * self.limits.max_drawdown_pct / 100:
            return RiskVerdict(False, "MAX_DRAWDOWN")

        exposure = await self.trades.active_exposure_by_user(bot.user_id)
        if exposure + capital > self.limits.max_user_exposure:
            return RiskVerdict(False, "MAX_USER_EXPOSURE")

        return ALLOWED
