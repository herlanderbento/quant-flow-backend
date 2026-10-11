import logging
from abc import ABC, abstractmethod
from datetime import datetime, timedelta, timezone
from typing import Callable

ALERT_LOGGER = logging.getLogger("quantflow.alerts")

SEVERITY_ERROR = "error"
SEVERITY_CRITICAL = "critical"


class IAlertSink(ABC):
    @abstractmethod
    async def send(self, key: str, severity: str, message: str, context: dict) -> None:
        pass


class AlertService:
    """Raises operational alerts, at most once per key within the cooldown window."""

    def __init__(
        self,
        sinks: list[IAlertSink],
        cooldown: timedelta = timedelta(minutes=15),
        clock: Callable[[], datetime] = lambda: datetime.now(timezone.utc),
    ):
        self.sinks = sinks
        self.cooldown = cooldown
        self.clock = clock
        self._last_sent: dict[str, datetime] = {}

    async def alert(self, key: str, severity: str, message: str, **context) -> bool:
        now = self.clock()
        last = self._last_sent.get(key)
        if last is not None and now - last < self.cooldown:
            return False
        self._last_sent[key] = now

        level = logging.CRITICAL if severity == SEVERITY_CRITICAL else logging.ERROR
        ALERT_LOGGER.log(
            level, "ALERT %s: %s", key, message,
            extra={"alert_key": key, "severity": severity, **context},
        )
        for sink in self.sinks:
            try:
                await sink.send(key, severity, message, context)
            except Exception:
                ALERT_LOGGER.exception("Alert sink %s failed", type(sink).__name__)
        return True
