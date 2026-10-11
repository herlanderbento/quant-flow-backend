import json
from datetime import datetime, timedelta, timezone

import httpx

from trader.application.alerts import SEVERITY_CRITICAL, AlertService, IAlertSink
from trader.infra.alerts import webhook_sink
from trader.infra.alerts.webhook_sink import WebhookAlertSink


class RecordingSink(IAlertSink):
    def __init__(self, fail=False):
        self.sent = []
        self.fail = fail

    async def send(self, key, severity, message, context):
        if self.fail:
            raise RuntimeError("sink down")
        self.sent.append((key, severity, message, context))


class Clock:
    def __init__(self):
        self.now = datetime(2026, 1, 1, tzinfo=timezone.utc)

    def __call__(self):
        return self.now


async def test_same_key_is_sent_once_per_cooldown():
    sink, clock = RecordingSink(), Clock()
    alerts = AlertService([sink], cooldown=timedelta(minutes=15), clock=clock)

    assert await alerts.alert("k", SEVERITY_CRITICAL, "first")
    assert not await alerts.alert("k", SEVERITY_CRITICAL, "again")
    assert await alerts.alert("other", SEVERITY_CRITICAL, "different key")
    clock.now += timedelta(minutes=16)
    assert await alerts.alert("k", SEVERITY_CRITICAL, "after cooldown")
    assert [s[0] for s in sink.sent] == ["k", "other", "k"]


async def test_failing_sink_does_not_break_other_sinks_or_caller(caplog):
    good = RecordingSink()
    alerts = AlertService([RecordingSink(fail=True), good])
    assert await alerts.alert("k", SEVERITY_CRITICAL, "msg", bot_id="b1")
    assert good.sent[0][3] == {"bot_id": "b1"}
    assert any("ALERT k" in r.getMessage() for r in caplog.records)


async def test_webhook_sends_only_safe_context(monkeypatch):
    captured = {}

    def handler(request: httpx.Request) -> httpx.Response:
        captured["body"] = json.loads(request.content)
        return httpx.Response(200)

    real_client = httpx.AsyncClient
    monkeypatch.setattr(
        webhook_sink.httpx, "AsyncClient",
        lambda **kw: real_client(transport=httpx.MockTransport(handler), **kw),
    )
    await WebhookAlertSink("https://hooks.example/abc").send(
        "bot.position_mismatch", "critical", "review",
        {"bot_id": "b1", "api_secret": "s3cr3t", "outcome": "POSITION_MISMATCH"},
    )
    body = captured["body"]
    assert body["context"] == {"bot_id": "b1", "outcome": "POSITION_MISMATCH"}
    assert "s3cr3t" not in json.dumps(body)
