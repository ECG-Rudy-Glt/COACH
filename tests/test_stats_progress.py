"""Écran Statistiques, lot « Progression » : règles ST6 à ST10."""
from datetime import date, datetime, timedelta

import pytest
from fastapi.testclient import TestClient

from app.main import app, get_repo
from app.questionnaire.models import Fact
from app.repo import MemoryRepo
from app.stats import progress as P

PW = "un-mot-de-passe-solide"
TODAY = date(2026, 10, 21)  # mercredi


def sess(day, exercises, status="done", sid=1, **logged):
    return {"id": sid, "day": day, "kind": "strength_upper", "title": "Haut du corps", "duration_min": 55, "status": status, "logged": {"exercises": exercises, **logged}}


def ex(name, *sets):
    return {"name": name, "sets": [{"kg": kg, "reps": reps} for kg, reps in sets]}


def run(gid, days_ago, km, minutes, hr=150, sport="run"):
    d = TODAY - timedelta(days=days_ago)
    return {"garmin_id": str(gid), "day": d, "started_at": datetime(d.year, d.month, d.day, 7), "sport": sport, "type_key": "running", "name": "Sortie", "duration_s": int(minutes * 60),
            "distance_m": km * 1000, "elevation_m": 0.0, "avg_hr": hr, "max_hr": 170, "calories": 500, "training_load": 80.0}


# ---- ST7 : charges, e1RM, répétitions ----

def test_st7_e1rm_only_for_loaded_sets_up_to_ten_reps():
    assert P.e1rm(100, 5) == 116.7 and P.e1rm(60, 10) == 80.0 and P.e1rm(100, 1) == 103.3
    assert P.e1rm(100, 12) is None and P.e1rm(None, 8) is None and P.e1rm(0, 8) is None and P.e1rm(50, 0) is None and P.e1rm("50", 5) is None
    assert P.valid_sets(ex("x", (None, 10), (20, 0), (-5, 8), ("a", 5))) == [{"kg": None, "reps": 10}]


def test_st7_curves_use_e1rm_with_loads_and_reps_without_and_ignore_skipped_sessions():
    d = lambda n: TODAY - timedelta(days=n)  # noqa: E731
    sessions = [sess(d(21), [ex("Squat", (80, 5), (80, 5)), ex("Tractions", (None, 6), (None, 5))], sid=1),
                sess(d(14), [ex("Squat", (85, 5), (70, 12))], sid=2),
                sess(d(7), [ex("Squat", (90, 3)), ex("Tractions", (None, 8))], sid=3),
                sess(d(7), [ex("Squat", (200, 5))], status="skipped", sid=4),
                sess(d(200), [ex("Squat", (50, 5))], sid=5)]
    curves = {c["name"]: c for c in P.exercise_curves(sessions, TODAY - timedelta(weeks=16))}
    sq = curves["Squat"]
    assert sq["mode"] == "e1rm" and [p["value"] for p in sq["points"]] == [93.3, 99.2, 99.0] and sq["sessions"] == 3  # séance sautée et séance trop ancienne écartées
    assert sq["change"]["abs"] == 5.7 and sq["points"][1]["kg"] == 85 and sq["points"][1]["sets"] == 2
    pu = curves["Tractions"]
    assert pu["mode"] == "reps" and [p["value"] for p in pu["points"]] == [6, 8] and pu["points"][0]["tonnage"] == 0
    assert P.exercise_curves([], TODAY) == [] and P.exercise_curves([sess(d(3), [ex("Mou", (None, 12))], status="planned")], d(30)) == []


def test_st7_one_point_per_day_and_single_session_has_no_change():
    s = [sess(TODAY, [ex("Développé", (60, 8))], sid=1), sess(TODAY, [ex("Développé", (65, 5))], sid=2)]
    c = P.exercise_curves(s, TODAY - timedelta(days=30))[0]
    assert len(c["points"]) == 1 and c["points"][0]["value"] == 76.0 and c["change"] is None


def test_st7_lift_records_heaviest_set_and_best_e1rm():
    s = [sess(TODAY - timedelta(days=9), [ex("Squat", (100, 3), (80, 10)), ex("Pompes", (None, 30))], sid=1), sess(TODAY - timedelta(days=2), [ex("Squat", (95, 5))], sid=2)]
    rec = P.lift_records(s)
    assert [r["name"] for r in rec] == ["Squat"]  # pas de record de charge sans charge
    assert rec[0]["kg"] == 100 and rec[0]["reps"] == 3 and rec[0]["day"] == (TODAY - timedelta(days=9)).isoformat()
    assert rec[0]["e1rm"] == 110.8 and rec[0]["e1rm_day"] == (TODAY - timedelta(days=2)).isoformat()
    assert P.lift_records([]) == []


def test_declared_lifts_come_from_the_performance_page():
    assert P.declared_lifts({"bench.squat": {"pr": {"weight": 120, "reps": 3, "year": 2024}, "now": {"weight": 100, "reps": 5}}, "bench.run_5k": {"pr": {"time": "21:00"}},
                             "bench.nope": {"pr": {"weight": 1}}},
                            app.state.bench_index) == [{"label": "Squat", "pr": {"kg": 120, "reps": 3, "e1rm": 132.0, "year": 2024}, "now": {"kg": 100, "reps": 5, "e1rm": 116.7, "year": None}}]


# ---- ST6 : records de course ----

def test_st6_run_records_keep_three_sources_apart_and_never_extrapolate():
    facts = {"bench.run_5k": {"pr": {"time": "21:00", "year": 2023}, "now": {"time": "22:10"}}, "bench.run_10k": {"pr": {"time": "pas un temps"}}}
    acts = [run(1, 3, 5.4, 28), run(2, 10, 7.0, 40), run(3, 20, 12.0, 66), run(4, 5, 4.2, 20), run(5, 8, 9.0, 40, sport="bike")]
    metrics = [{"day": TODAY - timedelta(days=40), "metric": "race_5k", "value": 1300.0}, {"day": TODAY - timedelta(days=2), "metric": "race_5k", "value": 1260.0}]
    five, ten = P.run_records(facts, acts, metrics)
    assert five["declared"] == {"pr": {"time": "21:00", "year": 2023}, "now": {"time": "22:10", "year": None}}
    assert five["measured"]["km"] == 5.4 and five["measured"]["pace"] == "5:11" and five["outings"] == 3  # sortie de 4,2 km et vélo écartés
    assert five["watch"] == {"time": "21:00", "day": (TODAY - timedelta(days=2)).isoformat()}
    assert ten["declared"] == {} and ten["measured"]["km"] == 12.0 and ten["measured"]["pace"] == "5:30" and ten["watch"] is None
    only = P.run_records({}, [run(1, 3, 4.0, 20)], [])
    assert only[0]["measured"] is None and only[1]["measured"] is None  # aucune sortie assez longue : rien n'est inventé


# ---- ST9 : volume hebdomadaire ----

def test_st9_weekly_volume_counts_a_linked_session_once_and_marks_the_current_week():
    acts = [run(1, 1, 10.0, 55), run(2, 9, 6.0, 35), run(3, 0, 0.0, 40, sport="strength")]
    sessions = [{**sess(TODAY - timedelta(days=1), [], sid=1), "kind": "run_easy", "logged": {"garmin_id": "1", "minutes": 55}},
                sess(TODAY - timedelta(days=2), [ex("Squat", (80, 5), (80, 5)), ex("Pompes", (None, 20))], sid=2, minutes=50)]
    w = P.weekly_volume(sessions, acts, TODAY, weeks=3)
    assert [x["monday"] for x in w] == ["2026-10-05", "2026-10-12", "2026-10-19"] and [x["current"] for x in w] == [False, False, True]
    cur = w[-1]
    assert cur["run_km"] == 10.0 and cur["minutes"] == 55 + 40 + 50 and cur["strength_sets"] == 3 and cur["tonnage_kg"] == 800  # 80 × 5 × 2
    assert w[1]["run_km"] == 6.0 and w[0]["minutes"] == 0 and w[0]["run_km"] == 0.0


# ---- ST10 : allure par sortie ----

def test_st10_pace_change_needs_enough_outings_on_both_sides():
    recent = [run(i, 2 + 6 * i, 8.0, 48) for i in range(4)]  # 6:00 /km
    before = [run(10 + i, 30 + 6 * i, 8.0, 52) for i in range(3)]  # 6:30 /km
    p = P.pace_outings(recent + before, TODAY)
    assert p["recent"]["pace_label"] == "6:00" and p["before"]["pace_label"] == "6:30" and p["change_s_per_km"] == -30 and len(p["outings"]) == 7
    few = P.pace_outings(recent + before[:2], TODAY)
    assert few["before"] is None and few["change_s_per_km"] is None
    short = P.pace_outings([run(1, 2, 0.8, 5)], TODAY)
    assert short["outings"] == [] and short["recent"] is None


# ---- ST8 : trajectoire ----

GOAL = {"status": "active", "kind": "performance", "target_date": date(2028, 9, 30), "priority": "principal", "title": "10 km en moins de 40 min",
        "details": {"sport": "course", "distance_km": 10, "target_value": 40, "unit": "min"}}
FACTS = {"bench.run_5k": {"pr": {"time": "21:00"}}, "bench.run_10k": {"pr": {"time": "45:30"}}}


def test_st8_trajectory_reuses_the_engine_and_labels_measured_points():
    metrics = [{"day": TODAY - timedelta(days=60), "metric": "race_10k", "value": 2760.0}, {"day": TODAY - timedelta(days=5), "metric": "race_10k", "value": 2700.0}]
    t = P.trajectory_block([GOAL], FACTS, metrics, TODAY)
    assert t["target"]["time"] == "40:00" and t["level"]["time"] == "45:30" and t["verdict"] in ("réaliste", "ambitieux", "très ambitieux") and t["milestones"]
    assert t["reference"][0]["minutes"] == 45.5 and t["reference"][-1] == {"day": "2028-09-30", "minutes": 40.0} and len(t["reference"]) <= 16
    assert [m["minutes"] for m in t["measured"]] == [46.0, 45.0] and t["measured_source"] == "race_10k"
    assert P.trajectory_block([], FACTS, metrics, TODAY) is None
    assert P.trajectory_block([{**GOAL, "status": "done"}], FACTS, [], TODAY) is None
    no_level = P.trajectory_block([GOAL], {}, [], TODAY)
    assert no_level["reference"] == [] and no_level["measured"] == [] and no_level["level"] is None
    # un temps de course de 5 km est converti au 10 km par la formule de Riegel (C10), pas autrement
    five = P.trajectory_block([{**GOAL, "details": {**GOAL["details"], "distance_km": 5, "target_value": 20}}], FACTS, [{"day": TODAY, "metric": "race_5k", "value": 1260.0}], TODAY)
    assert five["measured"] == [{"day": TODAY.isoformat(), "minutes": 21.0}]


# ---- API ----

@pytest.fixture
def ctx():
    from app.auth import reset_rate_limits

    reset_rate_limits()
    repo = MemoryRepo()
    app.dependency_overrides[get_repo] = lambda: repo
    c = TestClient(app)
    uid = c.post("/auth/register", json={"name": "R", "email": "sp@example.org", "password": PW}).json()["id"]
    yield c, uid, repo
    app.dependency_overrides.clear()


def test_progress_api_isolation_and_empty_state(ctx):
    c, uid, _ = ctx
    empty = c.get(f"/users/{uid}/stats/progress").json()
    assert empty["trajectory"] is None and empty["curves"] == [] and empty["records"]["lifts"] == [] and empty["pace"]["outings"] == [] and empty["volume"]["weekly_km_target"] is None
    assert all(r["measured"] is None and r["watch"] is None and r["declared"] == {} for r in empty["records"]["running"])
    other = c.post("/auth/register", json={"name": "E", "email": "sp2@example.org", "password": PW}).json()["id"]
    assert c.get(f"/users/{uid}/stats/progress").status_code == 403
    c.post("/auth/logout")
    assert c.get(f"/users/{other}/stats/progress").status_code == 401


def test_progress_api_with_data(ctx):
    c, uid, repo = ctx
    today = date.today()
    repo.add_facts(uid, [Fact(key="bench.run_10k", value={"pr": {"time": "45:30"}}), Fact(key="bench.squat", value={"pr": {"weight": 120, "reps": 3}})])
    c.post(f"/users/{uid}/goals", json={"title": "10 km sous 40 min", "kind": "performance", "target_date": (today + timedelta(days=700)).isoformat(), "priority": "principal",
                                         "details": {"distance_km": 10, "target_value": 40, "unit": "min"}})
    repo.add_sessions(uid, [{"day": today - timedelta(days=7 * i), "kind": "strength_upper", "title": "Haut", "duration_min": 55, "details": {}, "rules": [], "notes": []} for i in range(3)])
    for i, row in enumerate(repo.list_sessions(uid, today - timedelta(days=30), today + timedelta(days=1))):
        repo.update_session(uid, row["id"], "done", {"exercises": [ex("Squat", (80 + 5 * i, 5))]})
    repo.upsert_activities(uid, [run(1, 2, 10.5, 58)])
    repo.upsert_metrics(uid, [{"day": today - timedelta(days=3), "metric": "race_10k", "value": 2700.0}])
    d = c.get(f"/users/{uid}/stats/progress").json()
    assert d["trajectory"]["target"]["time"] == "40:00" and d["volume"]["weekly_km_target"] == 50 and d["trajectory"]["measured"][0]["minutes"] == 45.0
    assert d["curves"][0]["name"] == "Squat" and d["curves"][0]["mode"] == "e1rm" and len(d["curves"][0]["points"]) == 3
    assert d["records"]["lifts"][0]["name"] == "Squat" and d["records"]["declared_lifts"][0]["label"] == "Squat"
    ten = d["records"]["running"][1]
    assert ten["declared"]["pr"]["time"] == "45:30" and ten["measured"]["km"] == 10.5 and ten["watch"]["time"] == "45:00"
    assert d["volume"]["weeks"][-1]["run_km"] == 10.5 and len(d["volume"]["weeks"]) == 12 and d["pace"]["outings"][0]["pace_label"] == "5:31"
