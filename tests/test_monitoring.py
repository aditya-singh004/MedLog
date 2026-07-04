import json
import logging

from app.core.logging import JsonFormatter


def test_health_endpoints_and_request_id(client):
    live = client.get("/health/live")
    ready = client.get("/health/ready")
    health = client.get("/health")

    assert live.json() == {"status": "alive"}
    assert ready.json() == {"status": "ready", "database": "connected"}
    assert health.json()["database"] == "connected"
    assert live.headers.get("X-Request-ID")


def test_json_logs_exclude_unapproved_sensitive_fields():
    record = logging.LogRecord("medivault.test", logging.INFO, "", 0, "Request completed", (), None)
    record.request_id = "request-123"
    record.method = "GET"
    record.path = "/patient/medical-history"
    record.status_code = 200
    record.duration_ms = 12.5
    record.patient_email = "private@example.com"
    record.request_body = "sensitive clinical data"

    payload = json.loads(JsonFormatter().format(record))

    assert payload["request_id"] == "request-123"
    assert payload["path"] == "/patient/medical-history"
    assert "patient_email" not in payload
    assert "request_body" not in payload
