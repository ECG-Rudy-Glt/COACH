"""Séance faite hors plan, ajoutée à la main (ex. un « dos biceps » improvisé) : création, isolation, suppression, effet sur le plan et les statistiques."""
from datetime import date, timedelta

import pytest
from fastapi.testclient import TestClient

from app.auth import reset_rate_limits
from app.main import app, get_repo
from app.plan.level import lift_estimates
from app.repo import MemoryRepo
from app.stats import daily
from app.stats import regularity as R

PW = "un-mot-de-passe-solide"
TODAY = date.today()


@pytest.fixture
def env():
    reset_rate_limits()
    repo = MemoryRepo()
    app.dependency_overrides[get_repo] = lambda: repo
    c = TestClient(app)
    uid = c.post("/auth/register", json={"name": "R", "email": "m@example.org", "password": PW}).json()["id"]
    yield c, repo, uid
    app.dependency_overrides.clear()


def add(c, uid, **kw):
    body = {"day": TODAY.isoformat(), "kind": "strength_upper", "title": "  Dos   biceps ", "duration_min": 55, **kw}
    return c.post(f"/users/{uid}/plan/sessions", json=body)


def test_manual_session_is_stored_done_and_shown_in_the_week(env):
    c, repo, uid = env
    logged = {"rpe": 7, "exercises": [{"name": "Bench Press", "sets": [{"kg": 80, "reps": 5}, {}]}], "hack": "ignoré"}
    r = add(c, uid, logged=logged)
    assert r.status_code == 201
    s = r.json()
    assert s["status"] == "done" and s["title"] == "Dos biceps" and s["details"] == {"manual": True} and s["rules"] == []
    assert s["logged"]["source"] == "manual" and s["logged"]["rpe"] == 7 and "hack" not in s["logged"]  # même nettoyage qu'un retour de séance
    week = c.get(f"/users/{uid}/plan", params={"week": TODAY.isoformat()}).json()["sessions"]
    assert [x["id"] for x in week] == [s["id"]]
    assert add(c, uid, title="").json()["title"] == "Haut du corps"  # nom facultatif : libellé du type


def test_manual_session_survives_plan_regeneration(env):
    c, repo, uid = env
    for q, v in [("goal.sports", ["running", "strength"]), ("con.days", 4)]:
        c.post(f"/users/{uid}/answers", json={"question_id": q, "value": v})
    sid = add(c, uid, day=(TODAY + timedelta(days=0)).isoformat()).json()["id"]
    c.post(f"/users/{uid}/plan/generate", json={"weeks": 2})
    c.post(f"/users/{uid}/plan/generate", json={"weeks": 2})
    assert sid in {s["id"] for s in repo.list_sessions(uid, TODAY - timedelta(days=7), None)}


def test_manual_session_rejects_future_too_old_and_unknown_kind(env):
    c, _, uid = env
    assert add(c, uid, day=(TODAY + timedelta(days=1)).isoformat()).status_code == 422
    assert add(c, uid, day=(TODAY - timedelta(days=57)).isoformat()).status_code == 422
    assert add(c, uid, day=(TODAY - timedelta(days=56)).isoformat()).status_code == 201
    assert add(c, uid, kind="yoga").status_code == 422
    assert add(c, uid, duration_min=2).status_code == 422
    assert add(c, uid, title="x" * 81).status_code == 422


def test_only_manual_sessions_can_be_deleted_and_only_by_their_owner(env):
    c, repo, uid = env
    sid = add(c, uid).json()["id"]
    repo.add_sessions(uid, [{"day": TODAY, "kind": "run_easy", "title": "Footing", "duration_min": 40, "details": {}, "rules": ["C1"], "notes": []}])
    planned = next(s["id"] for s in repo.list_sessions(uid, TODAY, None) if s["id"] != sid)
    assert c.delete(f"/users/{uid}/plan/sessions/{planned}").status_code == 409  # une séance du plan se passe, elle ne se supprime pas
    c.post("/auth/logout")
    other = c.post("/auth/register", json={"name": "O", "email": "o@example.org", "password": PW}).json()["id"]
    assert c.delete(f"/users/{uid}/plan/sessions/{sid}").status_code in (401, 403)
    assert c.delete(f"/users/{other}/plan/sessions/{sid}").status_code == 404
    assert add(c, uid).status_code in (401, 403)
    c.post("/auth/logout")
    c.post("/auth/login", json={"email": "m@example.org", "password": PW})
    assert c.delete(f"/users/{uid}/plan/sessions/{sid}").json() == {"deleted": True}
    assert sid not in {s["id"] for s in repo.list_sessions(uid, TODAY - timedelta(days=7), None)}
    assert c.delete(f"/users/{uid}/plan/sessions/{sid}").status_code == 404


def test_manual_session_feeds_lifts_but_not_regularity():
    mon = TODAY - timedelta(days=TODAY.weekday())
    plan = [{"id": i, "day": mon, "kind": "run_easy", "title": "x", "duration_min": 40, "status": st, "details": {}, "logged": None}
            for i, st in enumerate(["done", "planned", "planned", "planned"])]
    extra = {"id": 9, "day": mon, "kind": "strength_upper", "title": "Dos biceps", "duration_min": 50, "status": "done", "details": {"manual": True},
             "logged": {"source": "manual", "exercises": [{"name": "Bench Press", "sets": [{"kg": 80, "reps": 5}]}]}}
    row = R.week_rows([*plan, extra], TODAY, weeks=1)[-1]
    assert (row["planned"], row["done"]) == (4, 1)  # ST11 : une séance en plus ne rattrape pas une séance prévue manquée
    wk = daily.week_block([*plan, extra], [], TODAY)
    assert (wk["planned"], wk["done"]) == (4, 1) and wk["minutes"] == 40 + 50  # mais ses minutes comptent
    assert lift_estimates([extra], TODAY)["bench"]["kg"] == 80  # C15 : les charges saisies comptent comme celles d'une séance du plan


def test_run_and_other_sport_keep_distance_hr_and_derive_pace(env):
    c, _, uid = env
    r = add(c, uid, kind="run_easy", title="", logged={"minutes": 50, "distance_km": 10, "avg_hr": 150, "rpe": 6, "note": "Bonnes jambes", "pace_s_km": 1})
    s = r.json()
    assert r.status_code == 201 and s["title"] == "Course facile" and s["logged"]["pace_s_km"] == 300  # allure déduite, la valeur du client est ignorée
    assert (s["logged"]["avg_hr"], s["logged"]["note"]) == (150, "Bonnes jambes")
    bike = add(c, uid, kind="sport_bike", title="", logged={"minutes": 90, "distance_km": 35}).json()
    assert bike["title"] == "Vélo" and bike["kind"] == "sport_bike"
    assert add(c, uid, kind="sport_other", title="Escalade").json()["title"] == "Escalade"


def test_out_of_range_manual_values_are_dropped_not_stored(env):
    c, _, uid = env
    s = add(c, uid, kind="run_easy", logged={"minutes": 50, "distance_km": -3, "avg_hr": 999, "rpe": 11, "max_hr": "x"}).json()["logged"]
    assert s["minutes"] == 50 and not {"distance_km", "avg_hr", "rpe", "max_hr", "pace_s_km"} & s.keys()


def test_edited_manual_session_still_feeds_estimated_level_through_the_api(env):
    c, _, uid = env
    s = add(c, uid, logged={"exercises": [{"name": "Bench Press", "sets": [{"kg": 60, "reps": 5}]}]}).json()
    assert c.get(f"/users/{uid}/benchmarks").json()["estimates"]["bench"]["kg"] == 60
    c.patch(f"/users/{uid}/plan/sessions/{s['id']}", json={"status": "done", "logged": {**s["logged"], "exercises": [{"name": "Bench Press", "sets": [{"kg": 80, "reps": 5}]}]}})
    assert c.get(f"/users/{uid}/benchmarks").json()["estimates"]["bench"]["kg"] == 80  # modification après coup prise en compte (C15)
    c.delete(f"/users/{uid}/plan/sessions/{s['id']}")
    assert "bench" not in c.get(f"/users/{uid}/benchmarks").json()["estimates"]
