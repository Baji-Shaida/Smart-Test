from fastapi.testclient import TestClient

from app.main import app


def test_health_returns_status():
    client = TestClient(app)
    body = client.get("/api/health").json()
    assert body["status"] == "ok"
    assert "ollama_reachable" in body
    assert "model" in body
