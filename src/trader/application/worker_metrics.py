from dataclasses import dataclass, field
from datetime import datetime

MAX_ERROR_LENGTH = 500


@dataclass
class WorkerMetrics:
    """In-memory counters of one worker process; persisted after every cycle."""

    worker_id: str
    trading_mode: str
    hostname: str
    started_at: datetime
    last_cycle_started_at: datetime | None = None
    last_cycle_finished_at: datetime | None = None
    last_market_data_at: datetime | None = None
    cycles_total: int = 0
    cycle_errors_total: int = 0
    consecutive_failures: int = 0
    max_cycle_gap_seconds: float = 0.0
    bots_last_cycle: int = 0
    outcome_counts: dict[str, int] = field(default_factory=dict)
    last_error: str | None = None
    last_audit_at: datetime | None = None
    audit_issues: int = 0
    audit_details: dict | None = None
    stopped_at: datetime | None = None
    _errors_this_cycle: int = 0

    def cycle_started(self, now: datetime, bots: int) -> None:
        if self.last_cycle_started_at is not None:
            gap = (now - self.last_cycle_started_at).total_seconds()
            self.max_cycle_gap_seconds = max(self.max_cycle_gap_seconds, gap)
        self.last_cycle_started_at = now
        self.bots_last_cycle = bots
        self._errors_this_cycle = 0

    def record_outcome(self, outcome: str) -> None:
        self.outcome_counts[outcome] = self.outcome_counts.get(outcome, 0) + 1

    def record_error(self, error: BaseException) -> None:
        self._errors_this_cycle += 1
        self.cycle_errors_total += 1
        self.last_error = f"{type(error).__name__}: {error}"[:MAX_ERROR_LENGTH]

    def market_data_seen(self, now: datetime) -> None:
        self.last_market_data_at = now

    def cycle_finished(self, now: datetime) -> None:
        self.cycles_total += 1
        self.last_cycle_finished_at = now
        self.consecutive_failures = (
            self.consecutive_failures + 1 if self._errors_this_cycle else 0
        )

    @property
    def failed_last_cycle(self) -> bool:
        return self._errors_this_cycle > 0
