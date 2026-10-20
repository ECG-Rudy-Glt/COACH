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


def test_background_jobs_start_with_the_lifespan(monkeypatch):
    from fastapi.testclient import TestClient

    import app.main as main

    started = []
    monkeypatch.setattr(main.garmin_scheduler, "start", lambda *a: started.append("garmin"))
    monkeypatch.setattr(main.coach_notify, "start", lambda *a: started.append("notify"))
    with TestClient(main.app):
        assert started == ["garmin", "notify"]
