"""Tests for the health endpoint."""

from fastapi.testclient import TestClient

from app.main import app


def test_health() -> None:
    """Check that the health endpoint answers 200 with a status payload."""

    client = TestClient(app)
    r = client.get("/api/health")
    assert r.status_code == 200
    assert r.json() == {"status": "ok"}
