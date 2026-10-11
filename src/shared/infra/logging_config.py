import json
import logging
import os
from datetime import datetime, timezone

from shared.application.log_context import current_log_context

SENSITIVE_MARKERS = ("secret", "api_key", "apikey", "password", "token", "authorization")
_STANDARD_ATTRS = set(vars(logging.makeLogRecord({}))) | {"message", "asctime"}


def _is_sensitive(key: str) -> bool:
    lowered = key.lower()
    return any(marker in lowered for marker in SENSITIVE_MARKERS)


def _safe(value):
    if isinstance(value, (str, int, float, bool)) or value is None:
        return value
    return str(value)


class JsonFormatter(logging.Formatter):
    """One JSON object per line, with correlation context and redacted sensitive fields."""

    def format(self, record: logging.LogRecord) -> str:
        payload = {
            "ts": datetime.fromtimestamp(record.created, tz=timezone.utc).isoformat(),
            "level": record.levelname,
            "logger": record.name,
            "msg": record.getMessage(),
        }
        extras = {k: v for k, v in vars(record).items() if k not in _STANDARD_ATTRS}
        for key, value in {**current_log_context(), **extras}.items():
            payload[key] = "[REDACTED]" if _is_sensitive(key) else _safe(value)
        if record.exc_info:
            payload["exc"] = self.formatException(record.exc_info)
        return json.dumps(payload, ensure_ascii=False)


class ContextTextFormatter(logging.Formatter):
    def format(self, record: logging.LogRecord) -> str:
        line = super().format(record)
        context = " ".join(
            f"{k}={'[REDACTED]' if _is_sensitive(k) else v}"
            for k, v in current_log_context().items()
        )
        return f"{line} [{context}]" if context else line


def configure_logging(default_format: str = "json") -> None:
    fmt = os.environ.get("LOG_FORMAT", default_format).lower()
    handler = logging.StreamHandler()
    handler.setFormatter(
        JsonFormatter()
        if fmt == "json"
        else ContextTextFormatter("%(asctime)s [%(levelname)s] %(name)s: %(message)s")
    )
    root = logging.getLogger()
    root.handlers[:] = [handler]
    root.setLevel(os.environ.get("LOG_LEVEL", "INFO").upper())
