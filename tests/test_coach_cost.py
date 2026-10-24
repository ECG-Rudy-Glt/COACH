"""Coût IA du mois : total serveur + part du compte, mois courant (fuseau Paris), aucune identité d'autrui."""
from datetime import UTC, datetime

import pytest
from fastapi.testclient import TestClient

from app.coach import service
from app.main import app, get_repo
from app.repo import MemoryRepo

PW = "un-mot-de-passe-solide"


@pytest.fixture
def two(monkeypatch):
    from app.auth import reset_rate_limits

    reset_rate_limits()
    monkeypatch.setenv("LLM_MONTHLY_BUDGET_EUR", "1")
    repo = MemoryRepo()
    app.dependency_overrides[get_repo] = lambda: repo
    a, b = TestClient(app), TestClient(app)
    ua = a.post("/auth/register", json={"name": "Alice-secrete", "email": "alice@example.org", "password": PW}).json()["id"]
    ub = b.post("/auth/register", json={"name": "Bob-secret", "email": "bob@example.org", "password": PW}).json()["id"]
    yield a, ua, b, ub, repo
    app.dependency_overrides.clear()


def test_cost_splits_server_total_and_own_share(two):
    a, ua, b, ub, repo = two
    repo.log_llm_call(ua, "chat", "claude-x", (10, 10), 0.10, True, None)
    repo.log_llm_call(ub, "chat", "claude-x", (10, 10), 0.30, True, None)
    repo.log_llm_call(ub, "meal", "claude-x", (10, 10), 0.20, True, None)
    repo.log_llm_call(ub, "weird", "claude-x", (0, 0), 0.0, False, "boom")  # échec : ni compté ni facturé
    r = a.get(f"/users/{ua}/coach/cost").json()
    assert r["spent_eur"] == 0.6 and r["limit_eur"] == 1.0 and r["percent"] == 60 and r["available"] and r["calls"] == 3
    assert r["mine"] == {"spent_eur": 0.1, "calls": 1}
    chat = next(u for u in r["usages"] if u["kind"] == "chat")
    assert chat["calls"] == 2 and chat["mine_calls"] == 1 and chat["mine_cost_eur"] == 0.1
    assert r["models"] == ["claude-x"]
    txt = str(r)
    assert "Bob" not in txt and "bob@" not in txt and "Alice" not in txt and "user_id" not in txt
    assert b.get(f"/users/{ub}/coach/cost").json()["mine"] == {"spent_eur": 0.5, "calls": 2}


def test_cost_requires_the_own_account(two):
    a, ua, b, ub, _ = two
    assert a.get(f"/users/{ub}/coach/cost").status_code in (401, 403, 404)
    assert TestClient(app).get(f"/users/{ua}/coach/cost").status_code in (401, 403)


def test_cost_cap_reached(two):
    a, ua, _, _, repo = two
    repo.log_llm_call(ua, "digest", "m", (1, 1), 1.5, True, None)
    r = a.get(f"/users/{ua}/coach/cost").json()
    assert not r["available"] and r["percent"] == 100


def test_only_current_month_in_paris_timezone():
    repo = MemoryRepo()
    repo.log_llm_call(1, "chat", "m", (1, 1), 0.5, True, None)
    repo._coach()[1][-1]["created_at"] = datetime(2026, 9, 30, 21, 59, tzinfo=UTC)  # 23:59 à Paris le 30/09 : septembre
    repo.log_llm_call(1, "chat", "m", (1, 1), 0.25, True, None)
    repo._coach()[1][-1]["created_at"] = datetime(2026, 9, 30, 22, 1, tzinfo=UTC)  # 00:01 à Paris le 01/10 : octobre
    now = datetime(2026, 10, 15, 12, tzinfo=UTC)
    r = service.cost_report(repo, 1, now)
    assert r["month"] == "2026-10" and r["spent_eur"] == 0.25 and r["calls"] == 1
    assert service.month_start_utc(now) == datetime(2026, 9, 30, 22, tzinfo=UTC)
