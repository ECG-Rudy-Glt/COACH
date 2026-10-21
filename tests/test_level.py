"""Niveau actuel estimé d'après les données récentes (C14 course, C15 force)."""
from datetime import date, timedelta

import pytest

from app.plan import level as L
from app.plan import trajectory as T
from app.plan.engine import build_profile, plan_weeks
from app.plan.strength import start_load

TODAY = date(2026, 10, 21)
GOAL = {"status": "active", "kind": "performance", "target_date": date(2028, 9, 30), "priority": "principal", "title": "10 km en moins de 40 min",
        "details": {"distance_km": 10, "target_value": 40, "unit": "min"}}
BASE = {"sports.practiced": ["running"], "constraints.training_days": 4, "constraints.weekday_session_max_min": 75, "constraints.weekend_session_max_min": 120,
        "running.weekly_km_8w": 25, "running.hr_max": 190, "bench.run_10k": {"pr": {"time": "38:00"}}}


def run(km: float, minutes: float, days_ago: int = 5, hr: int | None = None, climb: float = 0, type_key: str = "running", **extra):
    return {"day": TODAY - timedelta(days=days_ago), "type_key": type_key, "sport": "run", "distance_m": km * 1000, "duration_s": minutes * 60,
            "elevation_m": climb, "avg_hr": hr, "max_hr": None, **extra}


def test_sustained_effort_gives_an_estimate_converted_by_riegel():  # C14
    est = L.run_estimate([run(8, 38, hr=170)], TODAY, 10.0, 190)
    assert est and est["kind"] == "estimate" and est["minutes"] == pytest.approx(T.riegel(38, 8, 10), abs=0.01) and est["from_time"] == "38:00"


def test_without_heart_rate_an_outing_is_only_a_bound():  # C14
    est = L.run_estimate([run(8, 38)], TODAY, 10.0, 190)
    assert est and est["kind"] == "bound"
    assert L.run_estimate([run(8, 38, hr=150)], TODAY, 10.0, 190)["kind"] == "bound"  # FC intermédiaire : pas d'effort prouvé


def test_ignored_outings():  # C14 : ce qui ne dit rien du niveau
    ignored = [run(8, 50, hr=120), run(2.5, 12), run(8, 38, days_ago=70), run(8, 38, climb=400), run(8, 38, type_key="treadmill_running"), run(1.5, 8),
               run(40, 240), run(8, 100)]
    assert L.run_estimate(ignored, TODAY, 10.0, 190) is None
    assert L.run_estimate([run(8, 38, days_ago=-1)], TODAY, 10.0, 190) is None  # future


def test_slowest_sustained_distance_wins_but_never_slower_than_the_best_bound():  # C14
    fast5, slow10 = run(5, 20, hr=175), run(10, 46, hr=170)
    est = L.run_estimate([fast5, slow10], TODAY, 10.0, 190)
    assert est["kind"] == "estimate" and est["minutes"] == pytest.approx(46.0) and est["from_km"] == 10.0
    bound = run(9, 36)  # sans FC mais plus rapide que l'estimation soutenue : borne plus serrée
    assert L.run_estimate([fast5, slow10, bound], TODAY, 10.0, 190)["kind"] == "bound"


def test_priority_entered_then_watch_then_record():  # C14
    facts = {**BASE, "estimate.run": L.run_estimate([run(8, 38, hr=170)], TODAY, 10.0, 190)}
    assert T.level_info(facts, 10.0)["kind"] == "garmin" and T.level_is_record_only(facts, 10.0) is False
    assert T.level_info(BASE, 10.0)["kind"] == "record" and T.level_is_record_only(BASE, 10.0)
    entered = {**facts, "bench.run_10k": {"pr": {"time": "38:00"}, "now": {"time": "44:00"}}}
    info = T.level_info(entered, 10.0)
    assert info["kind"] == "saisi" and info["minutes"] == 44.0
    stale = {**facts, "estimate.run": {**facts["estimate.run"], "to_km": 5.0}}  # estimation faite pour une autre distance d'objectif
    assert T.level_info(stale, 10.0)["kind"] == "record"


def test_describe_exposes_source_kind_and_bound():  # C14
    target = T.pick_target([GOAL], TODAY)
    bound = {**BASE, "estimate.run": L.run_estimate([run(8, 38)], TODAY, 10.0, 190)}
    lv = T.describe(target, bound, [GOAL], TODAY)["level"]
    assert lv["source_kind"] == "garmin" and lv["bound"] is True and lv["record_only"] is False and lv["source_date"] == (TODAY - timedelta(days=5)).isoformat()
    assert "meilleure sortie récente" in lv["source"]
    rec = T.describe(target, BASE, [GOAL], TODAY)["level"]
    assert rec["source_kind"] == "record" and rec["record_only"] is True and rec["bound"] is False


def test_with_estimates_does_not_touch_entered_facts_and_needs_a_target():
    acts = [run(8, 38, hr=170)]
    out = L.with_estimates(BASE, acts, [], [GOAL], TODAY)
    assert out["bench.run_10k"] == BASE["bench.run_10k"] and "estimate.run" in out and "estimate.run" not in BASE
    assert "estimate.run" not in L.with_estimates(BASE, acts, [], [], TODAY)


def test_recent_estimate_slows_quality_paces_and_keeps_the_plan_invariants():  # C14 + G1, G5, S1-S6 (le moteur n'est pas modifié)
    goals = [GOAL]
    start = date(2027, 4, 12)
    old = plan_weeks(build_profile(BASE, goals, start), start, 4)
    slow = {**BASE, "estimate.run": {"minutes": 47.0, "to_km": 10.0, "from_km": 8.0, "from_time": "37:30", "day": "2027-04-01", "kind": "bound", "outings": 1}}
    prof = build_profile(slow, goals, start)
    assert prof.level_min == 47.0 and build_profile(BASE, goals, start).level_min == 38.0
    new = plan_weeks(prof, start, 4)
    assert [s.date for s in new] == [s.date for s in old]
    for week in (new, old):
        hard = sorted(s.date for s in week if s.kind in ("run_quality", "run_long"))
        assert all((b - a).days >= 2 for a, b in zip(hard, hard[1:], strict=False))  # G5


# --- C15 : force -------------------------------------------------------------------------------------------------------------------------------------

def sess(day_offset: int, name: str, sets: list[tuple], status: str = "done", slots=None):
    return {"day": TODAY - timedelta(days=day_offset), "status": status, "details": {"slots": slots or []},
            "logged": {"exercises": [{"name": name, "sets": [{"kg": k, "reps": r} for k, r in sets]}]}}


def test_lift_estimate_uses_epley_up_to_ten_reps():  # C15
    est = L.lift_estimates([sess(3, "Bench Press", [(80, 8), (85, 5), (60, 15)])], TODAY)
    assert est["bench"]["e1rm"] == pytest.approx(max(80 * (1 + 8 / 30), 85 * (1 + 5 / 30)), abs=0.1) and est["bench"]["kg"] == 80
    assert est["bench"]["day"] == (TODAY - timedelta(days=3)).isoformat()


def test_lift_estimate_ignores_high_reps_old_unfinished_and_unknown_exercises():  # C15
    assert L.lift_estimates([sess(3, "Bench Press", [(60, 15), (40, 25)])], TODAY) == {}
    assert L.lift_estimates([sess(100, "Bench Press", [(80, 5)])], TODAY) == {}
    assert L.lift_estimates([sess(3, "Bench Press", [(80, 5)], status="planned")], TODAY) == {}
    assert L.lift_estimates([sess(3, "Cable Fly", [(20, 10)])], TODAY) == {}
    assert L.lift_estimates([sess(3, "Bench Press", [(None, 8)])], TODAY) == {}


def test_lift_estimate_recognises_the_movement_noted_in_the_slot():  # C15 (nom localisé)
    slots = [{"exercise": {"name": "Développé couché"}, "movement": "bench"}]
    assert "bench" in L.lift_estimates([sess(2, "Développé couché", [(70, 6)], slots=slots)], TODAY)


def test_start_load_prefers_entered_then_estimate_then_record():  # C15
    slot = {"reps": "6-8"}
    both = {"bench.bench": {"pr": {"weight": 120, "reps": 1}, "now": {"weight": 80, "reps": 5}}, "estimate.bench.bench": {"e1rm": 100.0}}
    assert start_load("bench", both, slot) == start_load("bench", {"bench.bench": both["bench.bench"]}, slot)
    est_only = {"bench.bench": {"pr": {"weight": 120, "reps": 1}}, "estimate.bench.bench": {"e1rm": 90.0}}
    rec_only = {"bench.bench": est_only["bench.bench"]}
    assert start_load("bench", est_only, slot) < start_load("bench", rec_only, slot)


# --- API --------------------------------------------------------------------------------------------------------------------------------------------

def test_api_trajectory_level_source_kind_and_benchmark_estimates():
    from fastapi.testclient import TestClient

    from app.auth import reset_rate_limits
    from app.main import app, get_repo
    from app.repo import MemoryRepo

    reset_rate_limits()
    repo = MemoryRepo()
    app.dependency_overrides[get_repo] = lambda: repo
    try:
        c = TestClient(app)
        uid = c.post("/auth/register", json={"name": "R", "email": "lv@example.org", "password": "un-mot-de-passe-solide"}).json()["id"]
        today = date.today()
        c.post(f"/users/{uid}/goals", json={"title": "10 km en moins de 40 min", "kind": "performance", "priority": "principal", "target_date": (today + timedelta(days=700)).isoformat(),
                                             "details": {"distance_km": 10, "target_value": 40, "unit": "min"}})
        assert c.put(f"/users/{uid}/benchmarks", json={"items": {"run_10k": {"pr": {"time": "38:00"}}}}).status_code == 200
        assert c.get(f"/users/{uid}/plan").json()["trajectory"]["level"]["source_kind"] == "record"
        repo.upsert_activities(uid, [{"garmin_id": "1", "day": today - timedelta(days=4), "started_at": None, "sport": "run", "type_key": "running", "name": None, "duration_s": 2400,
                                      "distance_m": 8000.0, "elevation_m": 20.0, "avg_hr": None, "max_hr": None, "calories": None, "training_load": None}])
        lv = c.get(f"/users/{uid}/plan").json()["trajectory"]["level"]
        assert lv["source_kind"] == "garmin" and lv["bound"] is True and lv["record_only"] is False
        assert c.put(f"/users/{uid}/benchmarks", json={"items": {"run_10k": {"pr": {"time": "38:00"}, "now": {"time": "50:00"}}}}).status_code == 200
        assert c.get(f"/users/{uid}/plan").json()["trajectory"]["level"]["source_kind"] == "saisi"
        repo.add_sessions(uid, [{"day": today - timedelta(days=3), "kind": "strength_upper", "title": "Haut", "duration_min": 60, "details": {}, "rules": [], "notes": []}])
        sid = repo.list_sessions(uid, today - timedelta(days=5), today)[0]["id"]
        repo.update_session(uid, sid, "done", {"exercises": [{"name": "Bench Press", "sets": [{"kg": 80, "reps": 5}]}]})
        est = c.get(f"/users/{uid}/benchmarks").json()["estimates"]
        assert est["bench"]["e1rm"] == pytest.approx(93.3, abs=0.1) and c.get(f"/users/{uid}/benchmarks").json()["values"].get("bench") is None
    finally:
        app.dependency_overrides.clear()
