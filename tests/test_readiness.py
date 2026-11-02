"""Bilan de forme du jour (R1, R2, R4, R6) : seuils, allègement seulement, confirmation obligatoire, isolation entre comptes."""
from datetime import date, timedelta

import pytest
from fastapi.testclient import TestClient

import app.plan.api as plan_api
from app.auth import reset_rate_limits
from app.main import app, get_repo
from app.plan import readiness as RD
from app.repo import MemoryRepo

PW = "un-mot-de-passe-solide"
TODAY = date(2026, 10, 7)


class FixedDate(date):
    @classmethod
    def today(cls):
        return cls(2026, 10, 7)


def test_r6_degraded_needs_two_weak_signals_of_three():
    assert RD.is_degraded(2, 2, 1) and RD.is_degraded(3, 1, 4) and RD.is_degraded(1, 3, 5)
    assert not RD.is_degraded(1, 3, 3) and not RD.is_degraded(3, 3, 5) and not RD.is_degraded(5, 5, 1)  # un seul signal faible ne suffit pas


def test_r1_r4_proposals_only_lighten():
    st = {"degraded": True}
    ses = [{"id": 1, "status": "planned", "kind": "run_quality", "title": "Qualité", "duration_min": 50}, {"id": 2, "status": "planned", "kind": "run_easy", "title": "Footing", "duration_min": 40},
           {"id": 3, "status": "done", "kind": "run_easy", "title": "Fait", "duration_min": 40}, {"id": 4, "status": "planned", "kind": "run_easy", "title": "Court", "duration_min": 15}]
    out = {p["session_id"]: p for p in RD.proposals(st, ses)}
    assert out[1]["action"] == "swap_easy" and out[2]["duration_to"] == 28 and 3 not in out and 4 not in out  # 15 min ne descend pas plus bas
    assert RD.proposals({"degraded": False}, ses) == [] and RD.proposals(None, ses) == []


def test_r2_three_degraded_days_out_of_seven():
    m = [r for i in (0, 2, 4) for r in RD.rows(TODAY - timedelta(days=i), 2, 2, 3, False)]
    assert RD.week_alert(m, TODAY) and not RD.week_alert(m[:8], TODAY)


@pytest.fixture
def env(monkeypatch):
    reset_rate_limits()
    monkeypatch.setattr(plan_api, "date", FixedDate)
    repo = MemoryRepo()
    app.dependency_overrides[get_repo] = lambda: repo
    c = TestClient(app)
    uid = c.post("/auth/register", json={"name": "R", "email": "rd@example.org", "password": PW}).json()["id"]
    repo.add_sessions(uid, [{"day": TODAY, "kind": "run_quality", "title": "Qualité", "duration_min": 50, "details": {"zone": "z4"}, "rules": [], "notes": []},
                            {"day": TODAY + timedelta(days=1), "kind": "run_easy", "title": "Demain", "duration_min": 40, "details": {}, "rules": [], "notes": []}])
    yield c, repo, uid
    app.dependency_overrides.clear()


def test_checkin_proposes_then_applies_only_after_confirmation(env):
    c, repo, uid = env
    ok = c.post(f"/users/{uid}/plan/readiness", json={"energy": 4, "sleep": 4, "soreness": 1}).json()
    assert ok["state"]["degraded"] is False and ok["proposals"] == []
    r = c.post(f"/users/{uid}/plan/readiness", json={"energy": 1, "sleep": 2, "soreness": 4, "pain": True}).json()  # le bilan du jour se remplace
    assert r["state"]["degraded"] and r["proposals"][0]["action"] == "swap_easy" and r["pain_note"]
    assert next(s for s in repo.list_sessions(uid, TODAY, TODAY + timedelta(days=2)) if s["title"] == "Qualité")["kind"] == "run_quality"  # rien ne change sans confirmation
    sid = r["proposals"][0]["session_id"]
    assert c.post(f"/users/{uid}/plan/readiness/apply", json={"session_id": sid}).status_code == 200
    assert next(s for s in repo.list_sessions(uid, TODAY, TODAY + timedelta(days=2)) if s["id"] == sid)["kind"] == "run_easy"
    assert c.post(f"/users/{uid}/plan/readiness/apply", json={"session_id": sid}).status_code == 409  # déjà allégée : plus de proposition
    assert c.get(f"/users/{uid}/plan").json()["readiness"]["state"]["energy"] == 1


def test_checkin_validation_and_isolation(env):
    c, _repo, uid = env
    assert c.post(f"/users/{uid}/plan/readiness", json={"energy": 9, "sleep": 3, "soreness": 3}).status_code == 422
    assert c.post(f"/users/{uid}/plan/readiness/apply", json={"session_id": 999}).status_code == 409  # pas de bilan : rien à appliquer, même avec un identifiant arbitraire
    c.post("/auth/logout")
    c.post("/auth/register", json={"name": "E", "email": "rd2@example.org", "password": PW})
    assert c.get(f"/users/{uid}/plan/readiness").status_code == 403
