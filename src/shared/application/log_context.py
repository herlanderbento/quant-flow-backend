"""Correlation fields attached to every log record emitted inside a context."""
from contextlib import contextmanager
from contextvars import ContextVar
from typing import Iterator

_log_context: ContextVar[dict] = ContextVar("quantflow_log_context", default={})


def current_log_context() -> dict:
    return dict(_log_context.get())


@contextmanager
def log_context(**fields) -> Iterator[None]:
    """Adds fields (e.g. cycle_id, bot_id, client_order_id) for the duration of the block."""
    token = _log_context.set({**_log_context.get(), **{k: v for k, v in fields.items() if v is not None}})
    try:
        yield
    finally:
        _log_context.reset(token)


def bind_log_context(**fields) -> None:
    """Adds fields until the surrounding log_context block ends."""
    _log_context.set({**_log_context.get(), **{k: v for k, v in fields.items() if v is not None}})
