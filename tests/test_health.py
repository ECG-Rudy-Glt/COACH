from fastapi.testclient import TestClient

from app.main import app

client = TestClient(app)


def test_healthz():
    r = client.get("/healthz")
    assert r.status_code == 200
    assert r.json() == {"status": "ok"}


def test_version_uses_env(monkeypatch):
    monkeypatch.setenv("LLM_PROVIDER", "openrouter")
    r = client.get("/version")
    assert r.status_code == 200
    assert r.json()["llm_provider"] == "openrouter"
