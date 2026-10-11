"""/ops/worker-status is visible to every authenticated user, so its schema is an allow-list."""
from main import app

FORBIDDEN = {"last_error", "audit_details", "audit_issues", "outcome_counts", "bots_last_cycle"}


def test_worker_status_schema_excludes_cross_user_details():
    schema = app.openapi()
    response = schema["paths"]["/ops/worker-status"]["get"]["responses"]["200"]
    assert response["content"]["application/json"]["schema"] == {
        "$ref": "#/components/schemas/WorkerStatusResponse"
    }
    view = schema["components"]["schemas"]["WorkerStatusView"]
    assert view.get("additionalProperties") is False
    assert not FORBIDDEN & set(view["properties"])
