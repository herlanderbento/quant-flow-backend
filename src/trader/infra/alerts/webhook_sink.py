import httpx

from trader.application.alerts import IAlertSink

SAFE_CONTEXT_KEYS = {"bot_id", "trade_id", "worker_id", "outcome", "issues", "age_seconds"}


class WebhookAlertSink(IAlertSink):
    """POSTs a small JSON document to an operator-configured URL (e.g. a chat webhook)."""

    def __init__(self, url: str, timeout_seconds: float = 5.0):
        self.url = url
        self.timeout_seconds = timeout_seconds

    async def send(self, key: str, severity: str, message: str, context: dict) -> None:
        payload = {
            "text": f"[QuantFlow {severity.upper()}] {key}: {message}",
            "key": key,
            "severity": severity,
            # Only identifiers and counters leave the process; never credentials.
            "context": {k: str(v) for k, v in context.items() if k in SAFE_CONTEXT_KEYS},
        }
        async with httpx.AsyncClient(timeout=self.timeout_seconds) as client:
            response = await client.post(self.url, json=payload)
            response.raise_for_status()
