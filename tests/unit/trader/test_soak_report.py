from datetime import datetime, timedelta, timezone
from types import SimpleNamespace

from trader.infra.ops.soak_report import Thresholds, evaluate

NOW = datetime(2026, 10, 12, 12, tzinfo=timezone.utc)


def worker(started_h_ago, last_beat_s_ago, **overrides):
    data = dict(
        started_at=NOW - timedelta(hours=started_h_ago),
        last_heartbeat_at=NOW - timedelta(seconds=last_beat_s_ago),
        stopped_at=None, max_cycle_gap_seconds=12.0, cycles_total=4000,
        cycle_errors_total=3, consecutive_failures=0, outcome_counts={"NO_SIGNAL": 3990},
        bots_last_cycle=2, last_market_data_at=NOW - timedelta(seconds=10),
        last_audit_at=NOW - timedelta(minutes=2), audit_issues=0, last_error=None,
    )
    data.update(overrides)
    return SimpleNamespace(**data)


def results(workers, issues=()):
    criteria = evaluate(workers, NOW, NOW - timedelta(hours=30), Thresholds(), list(issues), {})
    return {c.name: c.passed for c in criteria}


def healthy_run():
    first = worker(26, 0, stopped_at=NOW - timedelta(hours=13),
                   last_heartbeat_at=NOW - timedelta(hours=13))
    second = worker(13 - 60 / 3600, 5)  # restarted 60 s after the first one stopped
    return [first, second]


def test_healthy_24h_run_with_restart_passes():
    assert all(results(healthy_run()).values())


def test_short_run_fails_duration():
    assert not results([worker(2, 5)])["duration"]


def test_no_restart_drill_fails():
    assert not results([worker(25, 5)])["restart_drill_performed"]


def test_long_restart_downtime_fails():
    first, second = healthy_run()
    second.started_at = first.last_heartbeat_at + timedelta(minutes=20)
    assert not results([first, second])["restart_recovery_time"]


def test_dead_worker_fails():
    first, second = healthy_run()
    second.last_heartbeat_at = NOW - timedelta(minutes=10)
    assert not results([first, second])["worker_alive_at_report"]


def test_error_rate_and_manual_review_outcomes_fail():
    first, second = healthy_run()
    second.cycle_errors_total = 500
    second.outcome_counts = {"POSITION_MISMATCH": 1}
    r = results([first, second])
    assert not r["cycle_error_rate"]
    assert not r["no_manual_review_outcomes"]


def test_ledger_issues_fail():
    assert not results(healthy_run(), issues=["trade x stuck in PENDING_OPEN"])["ledger_audit_at_report"]


def test_no_workers_fails():
    assert results([]) == {"worker_ran": False}
