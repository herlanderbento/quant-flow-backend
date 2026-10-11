import json
import logging

from shared.application.log_context import bind_log_context, log_context
from shared.infra.logging_config import JsonFormatter


def _format(message, **extra):
    record = logging.LogRecord("quantflow.test", logging.INFO, __file__, 1, message, None, None)
    for key, value in extra.items():
        setattr(record, key, value)
    return json.loads(JsonFormatter().format(record))


def test_json_line_carries_correlation_context():
    with log_context(cycle_id="c1", bot_id="b1"):
        bind_log_context(client_order_id="qf123")
        line = _format("entry filled", outcome="ENTRY_FILLED")
    assert line["msg"] == "entry filled"
    assert line["cycle_id"] == "c1"
    assert line["bot_id"] == "b1"
    assert line["client_order_id"] == "qf123"
    assert line["outcome"] == "ENTRY_FILLED"


def test_context_does_not_leak_outside_its_block():
    with log_context(bot_id="b1"):
        pass
    assert "bot_id" not in _format("after")


def test_sensitive_fields_are_redacted():
    with log_context(api_secret="s3cr3t"):
        line = _format("x", api_key="KEY", password="p", jwt_token="t")
    serialized = json.dumps(line)
    for value in ("s3cr3t", "KEY", '"p"', '"t"'):
        assert value not in serialized
    assert line["api_secret"] == "[REDACTED]"


def test_exceptions_are_included_as_traceback():
    try:
        raise ValueError("boom")
    except ValueError:
        import sys
        record = logging.LogRecord("x", logging.ERROR, __file__, 1, "failed", None, sys.exc_info())
    line = json.loads(JsonFormatter().format(record))
    assert "ValueError: boom" in line["exc"]
