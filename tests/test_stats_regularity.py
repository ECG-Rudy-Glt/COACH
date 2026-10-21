"""Écran Statistiques, lot « Régularité » : règles ST11 à ST13."""
from datetime import date, timedelta
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from app.main import app, get_repo
from app.repo import MemoryRepo
from app.stats import api as stats_api
from app.stats import regularity as R

PW = "un-mot-de-passe-solide"
TODAY = date(2026, 10, 21)  # mercredi
THIS = TODAY - timedelta(days=2)  # lundi de la semaine en cours


def s(monday_offset_weeks, status, n=1, weekday=0):
    """n séances d'un même statut, dans la semaine située `monday_offset_weeks` semaines avant la semaine en cours."""
    mon = THIS - timedelta(weeks=monday_offset_weeks)
    return [{"id": 0, "day": mon + timedelta(days=weekday), "kind": "run_easy", "title": "x", "duration_min": 40, "status": status, "logged": None} for _ in range(n)]


def week(offset, done, planned_open=0, skipped=0):
    return s(offset, "done", done) + s(offset, "planned", planned_open) + s(offset, "skipped", skipped)


def by_offset(rows, offset):
    return rows[-1 - offset]


# ---- ST11 : semaine tenue ----

def test_st11_a_week_is_met_from_75_percent_and_skipped_sessions_do_not_count_against():
    sessions = week(1, 3, 1) + week(2, 2, 1) + week(3, 2, 0, skipped=2) + week(4, 0, 0, skipped=3) + week(5, 1, 3)
    rows = R.week_rows(sessions, TODAY, weeks=8)
    assert by_offset(rows, 1)["met"] is True and by_offset(rows, 1)["planned"] == 4  # 3 sur 4 : 75 %
    assert by_offset(rows, 2)["met"] is False  # 2 sur 3
    assert by_offset(rows, 3)["met"] is True and by_offset(rows, 3)["skipped"] == 2  # séances passées volontairement : hors calcul
    assert by_offset(rows, 4)["met"] is None and by_offset(rows, 4)["planned"] == 0  # rien à juger
    assert by_offset(rows, 5)["met"] is False and by_offset(rows, 6)["met"] is None  # semaine sans séance : neutre
    assert [r["monday"] for r in rows][-1] == THIS.isoformat() and rows[-1]["current"] is True and len(rows) == 8


def test_st11_the_current_week_can_be_met_but_never_failed():
    behind = R.week_rows(s(0, "done", 1) + s(0, "planned", 3), TODAY, weeks=2)[-1]
    assert behind["met"] is None and behind["planned"] == 4 and behind["done"] == 1  # en cours : rien n'est jugé
    ahead = R.week_rows(s(0, "done", 3) + s(0, "planned", 1), TODAY, weeks=2)[-1]
    assert ahead["met"] is True


def test_st11_goal_of_the_week_is_the_engine_plan_and_nothing_else():
    row = R.week_rows(s(0, "done", 1) + s(0, "planned", 3) + s(0, "skipped", 1), TODAY, weeks=1)[-1]
    g = R.goal_block(row, TODAY)
    assert g == {"planned": 4, "done": 1, "skipped": 1, "needed": 3, "met": False, "days_left": 4}
    empty = R.goal_block(R.week_rows([], TODAY, weeks=1)[-1], TODAY)
    assert empty["planned"] == 0 and empty["needed"] == 0 and empty["met"] is False


# ---- ST12 : séries ----

def test_st12_a_quiet_week_keeps_the_streak_and_only_a_missed_finished_week_ends_it():
    # de la plus ancienne à la plus récente : tenue, tenue, (semaine sans séance), tenue, puis la semaine en cours
    sessions = week(4, 3) + week(3, 4) + week(1, 2)
    st = R.streaks(R.week_rows(sessions, TODAY, weeks=6))
    assert st == {"current": 3, "best": 3}
    broken = R.streaks(R.week_rows(week(4, 3) + week(3, 3) + week(2, 0, 3) + week(1, 3), TODAY, weeks=6))
    assert broken == {"current": 1, "best": 2}  # la meilleure série reste affichée, la série en cours repart
    assert R.streaks(R.week_rows([], TODAY, weeks=6)) == {"current": 0, "best": 0}
    in_progress = R.streaks(R.week_rows(week(2, 3) + week(1, 3) + s(0, "done", 1) + s(0, "planned", 3), TODAY, weeks=4))
    assert in_progress["current"] == 2  # la semaine en cours, pas encore tenue, ne casse pas la série
    ahead = R.streaks(R.week_rows(week(2, 3) + week(1, 3) + s(0, "done", 3), TODAY, weeks=4))
    assert ahead["current"] == 3


def test_st12_view_summary_counts_finished_weeks_only():
    v = R.regularity_view(week(1, 3, 1) + week(2, 2, 1) + week(3, 4) + s(0, "done", 1), TODAY)
    assert v["enabled"] is True and len(v["weeks"]) == 12 and v["summary"]["weeks_judged"] == 3 and v["summary"]["weeks_met"] == 2
    assert v["summary"]["sessions_done"] == 3 + 2 + 4 + 1 and v["summary"]["sessions_planned"] == 4 + 3 + 4 + 1 and v["streak"] == {"current": 2, "best": 2}
    assert v["goal"]["planned"] == 1 and v["goal"]["done"] == 1 and v["goal"]["met"] is True


# ---- ST13 : désactivable, sans pression ----

def test_st13_nothing_in_the_coach_or_notifications_reads_regularity():
    for f in Path(stats_api.__file__).resolve().parents[1].joinpath("coach").glob("*.py"):
        assert "app.stats" not in f.read_text(encoding="utf-8"), f.name  # aucune relance ni notification fondée sur les séries


@pytest.fixture
def ctx():
    from app.auth import reset_rate_limits

    reset_rate_limits()
    repo = MemoryRepo()
    app.dependency_overrides[get_repo] = lambda: repo
    c = TestClient(app)
    uid = c.post("/auth/register", json={"name": "R", "email": "rg@example.org", "password": PW}).json()["id"]
    yield c, uid, repo
    app.dependency_overrides.clear()


def test_st13_preference_turns_the_feature_off_and_nothing_is_computed(ctx, monkeypatch):
    c, uid, repo = ctx
    today = date.today()
    monday = today - timedelta(days=today.weekday())
    repo.add_sessions(uid, [{"day": monday - timedelta(days=7 * i), "kind": "run_easy", "title": "x", "duration_min": 40, "details": {}, "rules": [], "notes": []} for i in range(3)])
    for row in repo.list_sessions(uid, monday - timedelta(days=30), today + timedelta(days=1)):
        repo.update_session(uid, row["id"], "done", None)
    assert c.get(f"/users/{uid}/stats/preferences").json() == {"regularity": True}  # activé par défaut
    on = c.get(f"/users/{uid}/stats/regularity").json()
    assert on["enabled"] is True and on["streak"]["current"] >= 2
    assert c.put(f"/users/{uid}/stats/preferences", json={"regularity": False}).json() == {"regularity": False}
    monkeypatch.setattr(stats_api.regularity, "regularity_view", lambda *a, **k: (_ for _ in ()).throw(AssertionError("calculé alors que désactivé")))
    assert c.get(f"/users/{uid}/stats/regularity").json() == {"enabled": False}
    monkeypatch.undo()
    assert c.put(f"/users/{uid}/stats/preferences", json={"regularity": True}).json() == {"regularity": True}
    assert c.get(f"/users/{uid}/stats/regularity").json()["enabled"] is True


def test_regularity_api_isolation_and_validation(ctx):
    c, uid, _ = ctx
    assert c.put(f"/users/{uid}/stats/preferences", json={"regularity": "peut-être"}).status_code == 422
    assert c.put(f"/users/{uid}/stats/preferences", json={}).status_code == 422
    other = c.post("/auth/register", json={"name": "E", "email": "rg2@example.org", "password": PW}).json()["id"]
    for method, path in (("get", "regularity"), ("get", "preferences")):
        assert getattr(c, method)(f"/users/{uid}/stats/{path}").status_code == 403
    assert c.put(f"/users/{uid}/stats/preferences", json={"regularity": False}).status_code == 403
    assert c.get(f"/users/{other}/stats/regularity").json()["goal"]["planned"] == 0  # sans plan : rien d'inventé
    c.post("/auth/logout")
    assert c.get(f"/users/{other}/stats/regularity").status_code == 401
