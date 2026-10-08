"""Health endpoint reports service status."""

from fastapi.testclient import TestClient

from backend.app.main import app


def test_health_ok():
    client = TestClient(app)
    resp = client.get("/api/health")
    assert resp.status_code == 200
    body = resp.json()
    assert body["status"] == "ok"
    assert body["services"]["api"] == "up"
