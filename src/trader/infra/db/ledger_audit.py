"""Consistency checks of the trade ledger (and, in paper mode, of simulated fills)."""
from dataclasses import dataclass
from datetime import datetime, timedelta

from sqlalchemy import func, or_, select
from sqlalchemy.ext.asyncio import AsyncSession

from trader.domain.trade import (
    ACTIVE_TRADE_STATUSES,
    TRADE_STATUS_CLOSED,
    TRADE_STATUS_OPEN,
    TRADE_STATUS_PENDING_CLOSE,
    TRADE_STATUS_PENDING_OPEN,
)
from trader.infra.db.sql_models import TradeModel

MAX_LISTED = 20
PRICE_TOLERANCE = 1e-9


@dataclass(frozen=True)
class SimulatedFill:
    client_order_id: str
    side: str
    filled_quantity: float
    average_price: float
    filled_at: datetime


@dataclass(frozen=True)
class AuditResult:
    issues: list[str]

    @property
    def ok(self) -> bool:
        return not self.issues

    def as_details(self) -> dict:
        return {"issue_count": len(self.issues), "issues": self.issues[:MAX_LISTED]}


async def audit_trade_ledger(
    session: AsyncSession,
    *,
    now: datetime,
    stuck_after: timedelta,
    paper_fills: list[SimulatedFill] | None = None,
    fill_settle_time: timedelta = timedelta(seconds=60),
) -> AuditResult:
    issues: list[str] = []

    invalid_open = await session.execute(
        select(TradeModel.id).where(
            TradeModel.status == TRADE_STATUS_OPEN,
            or_(
                TradeModel.price_executed.is_(None),
                TradeModel.price_executed <= 0,
                TradeModel.entry_cost.is_(None),
                TradeModel.entry_cost <= 0,
                TradeModel.open_quantity.is_(None),
                TradeModel.open_quantity <= 0,
                TradeModel.open_quantity > TradeModel.quantity,
            ),
        )
    )
    issues += [f"open trade {row} has invalid entry data" for row in invalid_open.scalars()]

    invalid_closed = await session.execute(
        select(TradeModel.id).where(
            TradeModel.status == TRADE_STATUS_CLOSED,
            or_(
                TradeModel.closed_at.is_(None),
                TradeModel.pnl_usd.is_(None),
                TradeModel.pnl_pct.is_(None),
                TradeModel.open_quantity != 0,
            ),
        )
    )
    issues += [f"closed trade {row} is incomplete" for row in invalid_closed.scalars()]

    stuck = await session.execute(
        select(TradeModel.id, TradeModel.status).where(
            TradeModel.status.in_((TRADE_STATUS_PENDING_OPEN, TRADE_STATUS_PENDING_CLOSE)),
            TradeModel.updated_at < now - stuck_after,
        )
    )
    issues += [f"trade {row.id} stuck in {row.status}" for row in stuck]

    duplicated = await session.execute(
        select(TradeModel.bot_config_id)
        .where(TradeModel.status.in_(ACTIVE_TRADE_STATUSES))
        .group_by(TradeModel.bot_config_id)
        .having(func.count() > 1)
    )
    issues += [f"bot {row} has several active trades" for row in duplicated.scalars()]

    if paper_fills:
        issues += await _audit_paper_fills(session, paper_fills, now - fill_settle_time)

    return AuditResult(issues=issues)


async def _audit_paper_fills(
    session: AsyncSession, fills: list[SimulatedFill], settled_before: datetime
) -> list[str]:
    settled = [f for f in fills if f.filled_at <= settled_before]
    if not settled:
        return []
    ids = [f.client_order_id for f in settled]
    rows = await session.execute(
        select(TradeModel).where(
            or_(TradeModel.client_order_id.in_(ids), TradeModel.exit_client_order_id.in_(ids))
        )
    )
    by_entry, by_exit = {}, {}
    for trade in rows.scalars():
        by_entry[trade.client_order_id] = trade
        if trade.exit_client_order_id:
            by_exit[trade.exit_client_order_id] = trade

    issues = []
    for fill in settled:
        if fill.side == "BUY":
            trade = by_entry.get(fill.client_order_id)
            if trade is None:
                issues.append(f"paper fill {fill.client_order_id} has no trade")
            elif trade.status == TRADE_STATUS_PENDING_OPEN:
                issues.append(f"paper fill {fill.client_order_id} not applied to its trade")
            elif abs(float(trade.price_executed) - fill.average_price) > PRICE_TOLERANCE * fill.average_price + 1e-8:
                issues.append(f"paper fill {fill.client_order_id} price differs from trade")
        else:
            trade = by_exit.get(fill.client_order_id)
            if trade is None:
                # A partial exit's id is replaced by the next exit attempt of the same trade.
                continue
            if trade.status == TRADE_STATUS_PENDING_CLOSE:
                issues.append(f"paper exit {fill.client_order_id} not applied to its trade")
            elif trade.exit_price is not None and abs(
                float(trade.exit_price) - fill.average_price
            ) > PRICE_TOLERANCE * fill.average_price + 1e-8:
                issues.append(f"paper exit {fill.client_order_id} price differs from trade")
    return issues
