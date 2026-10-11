"""Objective PASS/FAIL evaluation of a paper-trading soak run, from the database.

    python -m trader.infra.ops.soak_report --since 2026-10-10T10:00:00Z --min-hours 24 \
        --out soak_evidence.json

Exit code 0 only if every criterion passes. Manual drills (database restart) are listed
as checklist items and must be confirmed by the operator with the run's logs.
"""
import argparse
import asyncio
import json
import sys
from dataclasses import asdict, dataclass
from datetime import datetime, timezone

from sqlalchemy import func, select

from shared.infra.db.config import settings
from shared.infra.db.database import AsyncSessionLocal, engine
import shared.infra.db.metadata  # noqa: F401  registers every ORM model
from trader.application.bot_cycle import DEFAULT_PENDING_GRACE
from trader.infra.db.ledger_audit import audit_trade_ledger
from trader.infra.db.sql_models import TradeModel, WorkerStatusModel

ALERTING_OUTCOMES = ("POSITION_MISMATCH", "INCONSISTENT", "EXIT_REJECTED", "EXIT_BELOW_MINIMUM")


@dataclass
class Criterion:
    name: str
    passed: bool
    evidence: str


@dataclass(frozen=True)
class Thresholds:
    min_hours: float = 24.0
    max_cycle_gap_seconds: float = 120.0
    max_restart_downtime_seconds: float = 300.0
    max_error_rate: float = 0.01
    max_heartbeat_age_seconds: float = 60.0
    max_market_data_age_seconds: float = 120.0
    max_audit_age_seconds: float = 900.0
    min_worker_restarts: int = 1


def evaluate(workers: list, now: datetime, since: datetime, thresholds: Thresholds,
             audit_issues: list[str], trade_counts: dict) -> list[Criterion]:
    criteria: list[Criterion] = []
    if not workers:
        return [Criterion("worker_ran", False, "no worker_status rows since the start time")]

    workers = sorted(workers, key=lambda w: w.started_at)
    first, last = workers[0], workers[-1]
    duration_h = (last.last_heartbeat_at - first.started_at).total_seconds() / 3600
    criteria.append(Criterion(
        "duration", duration_h >= thresholds.min_hours,
        f"{duration_h:.2f} h of heartbeats (required {thresholds.min_hours} h)"))

    heartbeat_age = (now - last.last_heartbeat_at).total_seconds()
    criteria.append(Criterion(
        "worker_alive_at_report", last.stopped_at is None
        and heartbeat_age <= thresholds.max_heartbeat_age_seconds,
        f"last heartbeat {heartbeat_age:.0f}s ago, stopped_at={last.stopped_at}"))

    max_gap = max(float(w.max_cycle_gap_seconds) for w in workers)
    criteria.append(Criterion(
        "cycle_continuity", max_gap <= thresholds.max_cycle_gap_seconds,
        f"largest gap between cycles {max_gap:.1f}s"))

    downtimes = [
        (nxt.started_at - prev.last_heartbeat_at).total_seconds()
        for prev, nxt in zip(workers, workers[1:])
    ]
    worst_downtime = max(downtimes, default=0.0)
    criteria.append(Criterion(
        "restart_recovery_time", worst_downtime <= thresholds.max_restart_downtime_seconds,
        f"{len(downtimes)} restart(s), worst downtime {worst_downtime:.0f}s"))
    criteria.append(Criterion(
        "restart_drill_performed", len(workers) - 1 >= thresholds.min_worker_restarts,
        f"{len(workers) - 1} worker restart(s) observed"))

    cycles = sum(w.cycles_total for w in workers)
    errors = sum(w.cycle_errors_total for w in workers)
    rate = errors / cycles if cycles else 1.0
    criteria.append(Criterion(
        "cycle_error_rate", cycles > 0 and rate <= thresholds.max_error_rate,
        f"{errors} errors in {cycles} cycles ({rate:.2%})"))
    criteria.append(Criterion(
        "no_ongoing_failures", last.consecutive_failures == 0,
        f"consecutive_failures={last.consecutive_failures}, last_error={last.last_error}"))

    outcomes: dict[str, int] = {}
    for w in workers:
        for key, value in (w.outcome_counts or {}).items():
            outcomes[key] = outcomes.get(key, 0) + value
    bad = {k: outcomes.get(k, 0) for k in ALERTING_OUTCOMES if outcomes.get(k, 0)}
    criteria.append(Criterion("no_manual_review_outcomes", not bad, f"outcomes={outcomes}"))

    if last.bots_last_cycle:
        md_age = (now - last.last_market_data_at).total_seconds() if last.last_market_data_at else None
        criteria.append(Criterion(
            "market_data_fresh", md_age is not None
            and md_age <= thresholds.max_market_data_age_seconds,
            f"last successful market data {md_age}s ago"))

    audit_age = (now - last.last_audit_at).total_seconds() if last.last_audit_at else None
    worker_audit_ok = all(w.audit_issues == 0 for w in workers)
    criteria.append(Criterion(
        "periodic_ledger_audits_clean", audit_age is not None
        and audit_age <= thresholds.max_audit_age_seconds and worker_audit_ok,
        f"last audit {audit_age}s ago; issues per worker={[w.audit_issues for w in workers]}"))
    criteria.append(Criterion(
        "ledger_audit_at_report", not audit_issues, f"issues={audit_issues[:10]}"))
    criteria.append(Criterion(
        "trade_activity_recorded", True, f"trades by status since start: {trade_counts}"))
    return criteria


async def collect(since: datetime):
    async with AsyncSessionLocal() as session:
        workers = (await session.execute(
            select(WorkerStatusModel).where(WorkerStatusModel.started_at >= since)
        )).scalars().all()
        audit = await audit_trade_ledger(
            session, now=datetime.now(timezone.utc), stuck_after=DEFAULT_PENDING_GRACE * 2)
        counts = dict((await session.execute(
            select(TradeModel.status, func.count())
            .where(TradeModel.executed_at >= since)
            .group_by(TradeModel.status)
        )).all())
    await engine.dispose()
    return list(workers), audit.issues, counts


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--since", required=True, help="ISO timestamp when the run started")
    parser.add_argument("--min-hours", type=float, default=24.0)
    parser.add_argument("--min-restarts", type=int, default=1)
    parser.add_argument("--out", default=None, help="write the evidence JSON here")
    args = parser.parse_args()

    since = datetime.fromisoformat(args.since.replace("Z", "+00:00"))
    workers, audit_issues, counts = asyncio.run(collect(since))
    now = datetime.now(timezone.utc)
    thresholds = Thresholds(min_hours=args.min_hours, min_worker_restarts=args.min_restarts)
    criteria = evaluate(workers, now, since, thresholds, audit_issues, counts)
    passed = all(c.passed for c in criteria)

    for c in criteria:
        print(f"[{'PASS' if c.passed else 'FAIL'}] {c.name}: {c.evidence}")
    print("Manual checklist (confirm from logs): database restart drill; no unhandled tracebacks "
          "stopping the worker; TRADING_MODE=paper in every worker_started log line.")
    print(f"RESULT: {'PASS' if passed else 'FAIL'} (trading_mode={settings.TRADING_MODE})")

    if args.out:
        evidence = {
            "generated_at": now.isoformat(),
            "since": since.isoformat(),
            "thresholds": asdict(thresholds),
            "result": "PASS" if passed else "FAIL",
            "criteria": [asdict(c) for c in criteria],
            "workers": [
                {k: (v.isoformat() if isinstance(v, datetime) else
                     float(v) if k == "max_cycle_gap_seconds" else v)
                 for k, v in vars(w).items() if not k.startswith("_")}
                for w in workers
            ],
            "trade_counts": counts,
            "audit_issues": audit_issues,
        }
        with open(args.out, "w", encoding="utf-8") as handle:
            json.dump(evidence, handle, indent=2, default=str)
        print(f"evidence written to {args.out}")
    return 0 if passed else 1


if __name__ == "__main__":
    sys.exit(main())
