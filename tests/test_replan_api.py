"""API de replanification : aperçu sans effet, application tracée, annulation, isolation entre comptes, phrase d'IA sans chiffre."""
from datetime import date, timedelta

import pytest
from fastapi.testclient import TestClient

import app.plan.api as plan_api
from app.auth import reset_rate_limits
from app.coach import replan_explain
from app.main import app, get_repo
from app.repo import MemoryRepo

PW = "un-mot-de-passe-solide"
WED = date(2026, 10, 7)


class FixedDate(date):
    @classmethod
    def today(cls):
        return cls(2026, 10, 7)


@pytest.fixture
def env(monkeypatch):
    reset_rate_limits()
    monkeypatch.setattr(plan_api, "date", FixedDate)
    repo = MemoryRepo()
    app.dependency_overrides[get_repo] = lambda: repo
    c = TestClient(app)
    uid = c.post("/auth/register", json={"name": "R", "email": "m@example.org", "password": PW}).json()["id"]
    for q, v in [("goal.sports", ["running", "strength"]), ("con.days", 4)]:
        c.post(f"/users/{uid}/answers", json={"question_id": q, "value": v})
    row = lambda d, kind, title, dur, status="planned": {"day": WED + timedelta(days=d), "kind": kind, "title": title, "duration_min": dur, "details": {}, "rules": ["G5"],  # noqa: E731
                                                          "notes": [], "status": status, "logged": {"minutes": dur} if status == "done" else None}
    repo.add_sessions(uid, [row(-1, "strength_lower", "Jambes", 60, "done"), row(0, "run_easy", "Footing", 45), row(0, "strength_upper", "Haut du corps", 50), row(3, "run_long", "Sortie longue", 80)])
    yield c, repo, uid
    app.dependency_overrides.clear()


def state(repo, uid):
    return [(r["title"], r["day"], r["status"], r["duration_min"]) for r in repo.list_sessions(uid, WED - timedelta(days=3), None)]


def test_preview_changes_nothing_and_cites_sources(env):
    c, repo, uid = env
    before = state(repo, uid)
    r = c.post(f"/users/{uid}/plan/replan/preview", json={})
    assert r.status_code == 200
    out = r.json()
    assert state(repo, uid) == before and out["fingerprint"] and out["explanation"] is None
    assert {a["rule"] for a in out["applied"]} >= {"G13"}
    g14 = [a for a in out["applied"] if a["rule"] == "G14"]
    assert not g14 or all(s["url"].startswith("https://") for s in g14[0]["sources"])
    thu = next(d for d in out["days"] if d["day"] == "2026-10-08")
    assert [s["title"] for s in thu["sessions"]] == ["Footing"]  # demain ; le haut du corps manqué trouve un autre jour libre plutôt que d'entasser
    assert sum(len(d["sessions"]) for d in out["days"]) == 3


def test_apply_trace_and_undo(env):
    c, repo, uid = env
    before = state(repo, uid)
    fp = c.post(f"/users/{uid}/plan/replan/preview", json={}).json()["fingerprint"]
    a = c.post(f"/users/{uid}/plan/replan/apply", json={"fingerprint": fp})
    assert a.status_code == 200 and a.json()["changed"] == 2
    rows = {r["title"]: r for r in repo.list_sessions(uid, WED - timedelta(days=3), None)}
    assert rows["Footing"]["day"] == WED + timedelta(days=1) and rows["Footing"]["details"]["moved_from"] == WED.isoformat() and "Replanifiée" in rows["Footing"]["notes"][-1]
    assert len(rows) == 4  # aucune séance ajoutée
    assert c.get(f"/users/{uid}/plan").json()["replan"]["id"] == a.json()["id"]
    assert c.post(f"/users/{uid}/plan/replan/{a.json()['id']}/undo").status_code == 200
    assert state(repo, uid) == before or {t[:3] for t in state(repo, uid)} == {t[:3] for t in before}
    assert c.post(f"/users/{uid}/plan/replan/{a.json()['id']}/undo").status_code == 409
    assert c.get(f"/users/{uid}/plan").json()["replan"] is None


def test_apply_refuses_stale_preview(env):
    c, repo, uid = env
    assert c.post(f"/users/{uid}/plan/replan/apply", json={"fingerprint": "0" * 24}).status_code == 409


def test_undo_refused_once_a_session_is_done(env):
    c, repo, uid = env
    fp = c.post(f"/users/{uid}/plan/replan/preview", json={}).json()["fingerprint"]
    mid = c.post(f"/users/{uid}/plan/replan/apply", json={"fingerprint": fp}).json()["id"]
    sid = next(r["id"] for r in repo.list_sessions(uid, WED, None) if r["title"] == "Footing")
    repo.update_session(uid, sid, "done", {"minutes": 40})
    assert c.post(f"/users/{uid}/plan/replan/{mid}/undo").status_code == 409


def test_isolation_between_accounts(env):
    c, repo, uid = env
    fp = c.post(f"/users/{uid}/plan/replan/preview", json={}).json()["fingerprint"]
    mid = c.post(f"/users/{uid}/plan/replan/apply", json={"fingerprint": fp}).json()["id"]
    other = TestClient(app)
    oid = other.post("/auth/register", json={"name": "S", "email": "s@example.org", "password": PW}).json()["id"]
    assert other.post(f"/users/{oid}/plan/replan/{mid}/undo").status_code == 404
    assert other.post(f"/users/{uid}/plan/replan/preview", json={}).status_code in (401, 403)
    assert TestClient(app).post(f"/users/{uid}/plan/replan/preview", json={}).status_code in (401, 403)
    assert other.post(f"/users/{oid}/plan/replan/preview", json={}).json()["empty"] is True


class FakeLLM:
    def __init__(self, text):
        self.text, self.calls = text, 0

    def configured(self):
        return True

    def complete(self, system, user, max_tokens, model=None, **kw):
        from app.coach.llm import LLMResult
        self.calls += 1
        assert not any(k in user for k in ("duration", "duree", "minutes")) and "@" not in user  # aucun chiffre calculé, aucune identité
        return LLMResult(text=self.text, model="fake", input_tokens=10, output_tokens=10)


def test_llm_sentence_is_optional_cached_and_digit_free(env):
    c, repo, uid = env
    out = c.post(f"/users/{uid}/plan/replan/preview", json={}).json()
    llm = FakeLLM("Votre footing passe à demain pour garder la sortie longue du week-end.")
    assert replan_explain.explain(repo, llm, uid, out, out["fingerprint"]) == llm.text
    assert replan_explain.explain(repo, llm, uid, out, out["fingerprint"]) == llm.text and llm.calls == 1  # mémorisée
    bad = FakeLLM("Footing de 45 minutes demain.")
    assert replan_explain.explain(repo, bad, uid, out, "autre-empreinte") is None  # un chiffre : rejetée
    assert replan_explain.clean("x" * 300) is None
