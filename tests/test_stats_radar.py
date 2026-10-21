"""Écran Statistiques, lot « Forme » (araignée) : règles ST14 à ST20."""
from datetime import date, datetime, timedelta

import pytest
from fastapi.testclient import TestClient

from app.main import app, get_repo
from app.repo import MemoryRepo
from app.stats import api as stats_api
from app.stats import radar as R

PW = "un-mot-de-passe-solide"
TODAY = date(2026, 10, 21)  # mercredi
THIS = TODAY - timedelta(days=2)  # lundi de la semaine en cours
FACTS = {"running.hr_max": 190}
LABELS = {"bench": "Développé couché", "squat": "Squat"}
GOAL = {"status": "active", "kind": "performance", "target_date": date(2028, 9, 30), "priority": "principal", "title": "10 km en moins de 40 min",
        "details": {"distance_km": 10, "target_value": 40, "unit": "min"}}


def run(days_ago, km, minutes, hr=175):
    d = TODAY - timedelta(days=days_ago)
    return {"garmin_id": f"{days_ago}-{km}", "day": d, "started_at": datetime(d.year, d.month, d.day, 7), "sport": "run", "type_key": "running", "name": "Sortie", "duration_s": int(minutes * 60),
            "distance_m": km * 1000, "elevation_m": 0.0, "avg_hr": hr, "max_hr": 190, "calories": 500, "training_load": 80.0}


def plan_session(week, status="done", weekday=0, minutes=40):
    return {"id": 0, "day": THIS - timedelta(weeks=week) + timedelta(days=weekday), "kind": "run_easy", "title": "x", "duration_min": minutes, "status": status, "logged": None, "details": {}}


def lift(days_ago, name, kg, reps=5):
    return {"id": 0, "day": TODAY - timedelta(days=days_ago), "kind": "strength_upper", "title": "x", "duration_min": 50, "status": "done", "details": {},
            "logged": {"exercises": [{"name": name, "sets": [{"kg": kg, "reps": reps}]}]}}


def world(runs=True, plan=True, lifts=True):
    """24 semaines : deux sorties par semaine (16 km, 5:00/km, FC soutenue), 4 séances prévues dont 3 faites, deux exercices de force."""
    acts, sessions = [], []
    for w in range(1, 25):
        if runs:
            acts += [run(w * 7 - 1, 10, 50), run(w * 7 - 3, 6, 30)]
        if plan and w <= 20:
            sessions += [plan_session(w, "done", d) for d in range(3)] + [plan_session(w, "planned", 3)]
        if lifts:
            age = w * 7 - 2
            sessions += [lift(age, "Bench Press", 80 if age <= 84 else 100), lift(age, "Barbell Full Squat", 100)]
    return sessions, acts


def view(sessions, acts, goals=(), regularity_on=True, facts=FACTS):
    return R.radar_view(sessions, acts, dict(facts), list(goals), LABELS, regularity_on, TODAY)


def axis(v, name):
    return next(a for a in v["axes"] if a["id"] == name)


def vrows(values, current=0):
    """Lignes de `weekly_volume` : `values` = (kilomètres, minutes) de la plus ancienne à la dernière semaine terminée, puis la semaine en cours."""
    rows = [{"monday": (THIS - timedelta(weeks=len(values) - i)).isoformat(), "run_km": km, "minutes": mn} for i, (km, mn) in enumerate(values)]
    return rows + [{"monday": THIS.isoformat(), "run_km": current, "minutes": current}]


# ---- ST14 : seulement des axes mesurés, jamais de score global ----

def test_st14_only_four_measured_axes_and_speed_recovery_are_declared_not_drawn():
    v = view(*world())
    assert [a["id"] for a in v["axes"]] == ["volume", "regularity", "endurance", "strength"]
    assert v["not_measured"] == ["speed", "recovery"]
    assert not {"score", "global", "total"} & set(v)  # pas de score global
    assert all(a["status"] == "ok" for a in v["axes"]) and v["chart"] is True


def test_st14_an_axis_without_data_is_not_drawn_and_says_why():
    v = view([], [])
    assert [a["status"] for a in v["axes"]] == ["insufficient"] * 4 and all(a["now"] is None and a["reason"] for a in v["axes"])
    assert v["chart"] is False and v["compare"] is False


def test_st14_the_polygon_needs_three_measured_axes():
    two = view(*world(runs=False, lifts=False))  # régularité et volume (minutes des séances saisies) seulement
    assert [a["id"] for a in two["axes"] if a["status"] == "ok"] == ["volume", "regularity"] and two["chart"] is False
    three = view(*world(runs=False))
    assert [a["id"] for a in three["axes"] if a["status"] == "ok"] == ["volume", "regularity", "strength"] and three["chart"] is True


# ---- ST15 : échelle = pourcentage de sa propre référence, plafonné à 100 ----

def test_st15_scale_is_a_percentage_of_the_own_reference_capped_at_100():
    assert R._pct(30, 40) == 75 and R._pct(40, 40) == 100 and R._pct(55, 40) == 100 and R._pct(0, 40) == 0 and R._pct(5, 0) == 0
    v = view(*world(), goals=[GOAL])
    for a in v["axes"]:
        assert isinstance(a["now"]["score"], int) and 0 <= a["now"]["score"] <= 100
    assert {axis(v, "volume")["now"]["reference_kind"], axis(v, "endurance")["now"]["reference_kind"]} == {"goal"}  # références : objectif du plan et temps visé, rien d'autre
    capped = R.volume_axis(vrows([(10, 0)] * 16 + [(40, 0)] * 4), None)["now"]
    assert capped["score"] == 100 and capped["value"] == 40.0  # la valeur brute reste exacte quand le score est plafonné


# ---- ST16 : volume ----

def test_st16_volume_is_the_mean_of_the_last_four_finished_weeks_against_the_plan_target():
    a = R.volume_axis(vrows([(10, 100)] * 16 + [(20, 0), (30, 0), (30, 0), (40, 0)], current=99), 40)  # la semaine en cours (99) est exclue
    assert a["unit"] == "km" and a["now"]["value"] == 30.0 and a["now"]["reference"] == 40.0 and a["now"]["reference_kind"] == "goal" and a["now"]["score"] == 75
    assert a["now"]["weeks"] == [20, 30, 30, 40]


def test_st16_without_target_the_reference_is_the_best_week_of_the_twelve_before_and_non_runners_count_minutes():
    a = R.volume_axis(vrows([(0, 0)] * 4 + [(0, 60)] * 8 + [(0, 200)] + [(0, 60)] * 3 + [(0, 100)] * 4), None)
    assert a["unit"] == "min" and a["now"]["reference"] == 200.0 and a["now"]["reference_kind"] == "best" and a["now"]["score"] == 50
    assert a["before"]["reference"] == 60.0 and a["before"]["value"] == 95.0  # quatre semaines plus tôt : fenêtre et référence décalées


def test_st16_too_little_history_gives_no_volume_axis():
    a = R.volume_axis(vrows([(0, 0)] * 17 + [(0, 50), (0, 50), (0, 50)]), None)
    assert a["status"] == "insufficient" and a["now"] is None and a["reason"] == "short_history"  # moins de 3 semaines non vides avant la période


# ---- ST17 : régularité ----

def reg_sessions(done, planned_open=0, skipped=0, weeks=range(1, 17)):
    out = []
    for w in weeks:
        out += [plan_session(w, "done", d) for d in range(done)] + [plan_session(w, "planned", 3) for _ in range(planned_open)] + [plan_session(w, "skipped", 4) for _ in range(skipped)]
    return out


def test_st17_regularity_is_the_share_of_planned_sessions_done_over_twelve_finished_weeks():
    a = R.regularity_axis(reg_sessions(3, 1) + [plan_session(0, "planned", 0)] * 5, TODAY, True)  # la semaine en cours n'entre pas
    assert a["now"]["score"] == 75 and a["now"]["done"] == 36 and a["now"]["planned"] == 48 and a["now"]["weeks"] == 12
    assert R.regularity_axis(reg_sessions(2, 0, skipped=2), TODAY, True)["now"]["score"] == 100  # une séance passée volontairement sort du calcul
    assert a["before"]["score"] == 75


def test_st17_regularity_needs_enough_planned_sessions_and_follows_the_profile_switch():
    few = R.regularity_axis(reg_sessions(1, 0, weeks=range(1, 4)), TODAY, True)
    assert few["status"] == "insufficient" and few["reason"] == "few_planned" and few["now"] is None
    off = R.regularity_axis(reg_sessions(3, 1), TODAY, False)
    assert off == {"id": "regularity", "status": "off", "reason": "off", "now": None, "before": None, "delta": None}  # ST13 : désactivée, rien n'est calculé


# ---- ST18 : endurance ----

def test_st18_endurance_is_the_watch_measured_level_against_the_goal_time():
    a = R.endurance_axis([run(5, 10, 50)], FACTS, [GOAL], TODAY)
    assert a["now"]["score"] == 80 and a["now"]["time"] == "50:00" and a["now"]["reference_kind"] == "goal" and a["now"]["reference_time"] == "40:00" and a["now"]["kind"] == "estimate"
    b = R.endurance_axis([run(5, 10, 50), run(40, 10, 60)], FACTS, [GOAL], TODAY)
    assert b["before"]["score"] == 67  # il y a 4 semaines : la sortie de 60 min était la meilleure de la fenêtre de 8 semaines


def test_st18_declared_times_and_records_do_not_count_and_a_run_without_heart_rate_is_a_bound():
    facts = {**FACTS, "bench.run_10k": {"now": {"time": "30:00"}, "pr": {"time": "29:00"}}}
    assert R.endurance_axis([run(5, 10, 50)], facts, [GOAL], TODAY)["now"]["minutes"] == 50.0  # le temps saisi (30:00) est ignoré
    assert R.endurance_axis([run(5, 10, 50, hr=None)], FACTS, [GOAL], TODAY)["now"]["kind"] == "bound"  # sans FC : un minimum, signalé
    none = R.endurance_axis([], FACTS, [GOAL], TODAY)
    assert none["status"] == "insufficient" and none["reason"] == "no_run" and none["now"] is None


def test_st18_without_goal_the_reference_is_the_best_earlier_estimate_on_ten_km():
    acts = [run(5, 10, 48), run(75, 10, 45), run(100, 10, 47)]  # les sorties de 75 et 100 jours sont hors de la fenêtre actuelle de 56 jours
    a = R.endurance_axis(acts, FACTS, [], TODAY)
    assert a["now"]["to_km"] == 10.0 and a["now"]["reference_kind"] == "best" and a["now"]["reference_time"] == "45:00" and a["now"]["score"] == 94
    lone = R.endurance_axis([run(5, 10, 48)], FACTS, [], TODAY)
    assert lone["status"] == "insufficient" and lone["reason"] == "no_reference"  # rien de plus ancien pour se comparer : pas de repère inventé


# ---- ST19 : force ----

def test_st19_strength_is_the_mean_of_per_lift_e1rm_against_the_previous_twelve_weeks():
    sessions = [lift(10, "Bench Press", 80), lift(100, "Bench Press", 100), lift(12, "Barbell Full Squat", 100), lift(110, "Barbell Full Squat", 100), lift(20, "Bench Press", 60, reps=15)]
    a = R.strength_axis(sessions, TODAY, LABELS)
    assert a["now"]["score"] == 90 and [(x["label"], x["score"]) for x in a["now"]["lifts"]] == [("Développé couché", 80), ("Squat", 100)]
    assert a["now"]["lifts"][0]["e1rm"] == pytest.approx(93.3, abs=0.1) and a["now"]["lifts"][0]["reference"] == pytest.approx(116.7, abs=0.1)


def test_st19_strength_needs_two_lifts_measured_in_both_periods():
    one = [lift(10, "Bench Press", 80), lift(100, "Bench Press", 100), lift(12, "Barbell Full Squat", 100)]  # le squat n'a pas de période précédente
    a = R.strength_axis(one, TODAY, LABELS)
    assert a["status"] == "insufficient" and a["reason"] == "few_lifts" and a["now"] is None
    assert R.strength_axis([lift(10, "Bench Press", 60, reps=15), lift(100, "Bench Press", 80)], TODAY, LABELS)["now"] is None  # plus de 10 répétitions : pas d'e1RM (ST7)


# ---- ST20 : comparaison avec il y a 4 semaines ----

def test_st20_comparison_is_drawn_only_when_every_drawn_axis_has_a_value_four_weeks_ago():
    v = view(*world())
    assert v["compare"] is True and v["compare_weeks"] == 4
    s = axis(v, "strength")
    assert (s["now"]["score"], s["before"]["score"], s["delta"]) == (90, 100, -10)  # l'écart est calculé par le moteur, en points
    sessions, acts = world(plan=False, lifts=False)
    sessions += [plan_session(w, "done", d) for w in range(1, 7) for d in range(3)]  # 6 semaines de plan : pas de valeur d'il y a 4 semaines pour la régularité
    short = view(sessions, acts)
    assert axis(short, "regularity")["status"] == "ok" and axis(short, "regularity")["before"] is None
    assert short["chart"] is True and short["compare"] is False


# ---- API ----

@pytest.fixture
def ctx():
    from app.auth import reset_rate_limits

    reset_rate_limits()
    repo = MemoryRepo()
    app.dependency_overrides[get_repo] = lambda: repo
    c = TestClient(app)
    uid = c.post("/auth/register", json={"name": "R", "email": "radar@example.org", "password": PW}).json()["id"]
    yield c, uid, repo
    app.dependency_overrides.clear()


def test_radar_api_empty_account_draws_nothing_and_isolation_holds(ctx):
    c, uid, _ = ctx
    d = c.get(f"/users/{uid}/stats/radar").json()
    assert d["chart"] is False and all(a["status"] == "insufficient" for a in d["axes"])
    other = c.post("/auth/register", json={"name": "E", "email": "radar2@example.org", "password": PW}).json()["id"]
    assert c.get(f"/users/{uid}/stats/radar").status_code == 403
    c.post("/auth/logout")
    assert c.get(f"/users/{other}/stats/radar").status_code == 401


def test_radar_api_switching_regularity_off_computes_nothing_for_that_axis(ctx, monkeypatch):
    c, uid, _ = ctx
    assert axis(c.get(f"/users/{uid}/stats/radar").json(), "regularity")["status"] == "insufficient"
    assert c.put(f"/users/{uid}/stats/preferences", json={"regularity": False}).status_code == 200
    monkeypatch.setattr(stats_api.regularity, "week_rows", lambda *a, **k: (_ for _ in ()).throw(AssertionError("calculé alors que désactivé")))
    assert axis(c.get(f"/users/{uid}/stats/radar").json(), "regularity")["status"] == "off"
