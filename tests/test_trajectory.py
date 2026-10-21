from datetime import date, timedelta

import pytest
from fastapi.testclient import TestClient

from app.main import app, get_repo
from app.plan import trajectory as T
from app.plan.cycles import cycle_for, describe, target_phase
from app.plan.engine import advice, build_profile, plan_weeks
from app.repo import MemoryRepo

TODAY = date(2026, 12, 8)  # mardi
RACE = date(2028, 9, 30)
FACTS = {
    "sports.practiced": ["running", "strength", "trail"], "constraints.training_days": 5,
    "constraints.weekday_session_max_min": 75, "constraints.weekend_session_max_min": 180,
    "running.weekly_km_8w": 12.9, "running.weekly_km_12m": 8.2, "running.hr_max": 190, "running.longest_recent_min": 45,
    "strength.sessions_per_week": 3, "history.recent_break": "non", "history.injuries": ["aucune"],
    "bench.run_5k": {"pr": {"time": "21:00"}}, "bench.run_10k": {"pr": {"time": "45:30"}},
}
SUB40 = {"status": "active", "kind": "performance", "target_date": RACE, "priority": "principal", "title": "10 km en moins de 40 min",
         "details": {"sport": "course", "distance_km": 10, "target_value": 40, "unit": "min"}}
ULTRA = {"status": "active", "kind": "event", "target_date": None, "priority": "si possible", "title": "Ultra-trail (date à définir)", "details": {}}


def test_time_parsing_and_riegel():
    assert T.parse_time("45:30") == 45.5 and T.parse_time("1:05:20") == pytest.approx(65.333, abs=0.01)
    assert all(T.parse_time(x) is None for x in ("", "abc", "45:70", "-3:10", None, 45))
    assert T.riegel(21.0, 5, 10) == pytest.approx(43.78, abs=0.05)  # C10
    assert T.fmt_time(40.0) == "40:00" and T.fmt_time(65.5) == "1:05:30" and T.fmt_pace(3.9833) == "3:59"


def test_current_level_keeps_the_slowest_equivalent_and_prefers_now():
    lvl = T.current_level(FACTS, 10.0)
    assert lvl and lvl[0] == 45.5  # 5 km 21:00 donne ≈ 43:44, le 10 km réel 45:30 est plus lent : on garde le prudent
    better = {**FACTS, "bench.run_10k": {"pr": {"time": "45:30"}, "now": {"time": "43:00"}}}
    assert T.current_level(better, 10.0)[0] == pytest.approx(43.0, abs=0.01)  # C14 : le temps « actuel » saisi prime sur tout record, même d'une autre distance
    assert T.current_level({"sports.practiced": ["running"]}, 10.0) is None


def test_pick_target_only_takes_dated_run_performance_goals():
    assert T.pick_target([SUB40], TODAY)["time_min"] == 40
    assert T.pick_target([{**SUB40, "kind": "event"}], TODAY) is None
    assert T.pick_target([{**SUB40, "target_date": None}], TODAY) is None
    assert T.pick_target([{**SUB40, "target_date": date(2026, 1, 1)}], TODAY) is None
    assert T.pick_target([{**SUB40, "details": {"distance_km": 100, "target_value": 40}}], TODAY) is None  # hors du champ de la trajectoire
    assert T.pick_target([{**SUB40, "details": {"distance_km": 10, "target_value": 40, "unit": "kg"}}], TODAY) is None
    assert T.pick_target([{**SUB40, "details": {"distance_km": 10, "target_value": 2400, "unit": "s"}}], TODAY)["time_min"] == 40
    later = {**SUB40, "priority": "important", "target_date": date(2027, 5, 1)}
    assert T.pick_target([later, SUB40], TODAY)["date"] == RACE  # le principal prime sur le plus proche


def test_target_phase_boundaries():
    assert [target_phase(n) for n in (None, 40, 22, 21, 10, 9, 2, 1, 0)] == ["base", "base", "base", "threshold", "threshold", "specific", "specific", "taper", "race"]


def test_describe_for_the_reference_goal():
    d = T.describe(T.pick_target([SUB40], TODAY), FACTS, [SUB40, ULTRA], TODAY)
    assert d["verdict"] == "réaliste" and d["gap_pct"] == 12.1 and d["level"]["time"] == "45:30"
    assert d["weekly_km_target"] == 50  # C12 : sub 40 au 10 km
    macros = [p["macro"] for p in d["phases"]]
    assert macros == ["base", "threshold", "specific", "taper", "race"]
    assert sum(p["weeks"] for p in d["phases"]) == d["weeks_left"] + 1
    assert [p["weeks"] for p in d["phases"][1:]] == [12, 8, 1, 1]
    assert d["phases"][-1]["end"] >= RACE.isoformat() >= d["phases"][-1]["start"]
    tests = d["milestones"]
    assert len(tests) >= 6 and tests[0]["label"] == "Test 5 km"
    times = [int(m["target_time"].split(":")[0]) * 60 + int(m["target_time"].split(":")[1]) for m in tests]
    assert times == sorted(times, reverse=True)  # les temps de contrôle descendent vers l'objectif
    assert any("n'a pas de date" in w for w in d["warnings"])


def test_describe_flags_unrealistic_gaps_and_unknown_level():
    crazy = T.describe({**T.pick_target([SUB40], TODAY), "time_min": 30.0, "date": TODAY + timedelta(days=180)}, FACTS, [], TODAY)
    assert crazy["verdict"] == "très ambitieux" and any("très ambitieux" in w for w in crazy["warnings"])
    unknown = T.describe(T.pick_target([SUB40], TODAY), {"sports.practiced": ["running"]}, [], TODAY)
    assert unknown["verdict"] == "inconnu" and unknown["level"] is None and unknown["milestones"] == []
    done = T.describe(T.pick_target([SUB40], TODAY), {**FACTS, "bench.run_10k": {"pr": {"time": "39:30"}}, "bench.run_5k": {"pr": {"time": "19:00"}}}, [], TODAY)
    assert done["verdict"] == "atteint"


def test_dated_ultra_inside_the_speed_window_is_flagged_but_not_one_after():
    near = {**ULTRA, "target_date": RACE - timedelta(weeks=8)}
    far = {**ULTRA, "target_date": RACE - timedelta(weeks=40)}
    after = {**ULTRA, "target_date": RACE + timedelta(weeks=12)}
    t = T.pick_target([SUB40], TODAY)
    assert any("se gênent" in w for w in T.describe(t, FACTS, [near], TODAY)["warnings"])
    assert any("se gênent" in w for w in T.describe(t, FACTS, [{**ULTRA, "target_date": RACE + timedelta(weeks=1)}], TODAY)["warnings"])
    assert not any("se gênent" in w or "n'a pas de date" in w for w in T.describe(t, FACTS, [far, after], TODAY)["warnings"])


def test_volume_ceiling_applies_while_the_goal_is_far():
    """C12 : sans événement proche, le volume ne monte plus sans limite ; la même personne sans objectif de performance n'est pas plafonnée."""
    big = {**FACTS, "running.weekly_km_8w": 80, "running.weekly_km_12m": 80, "running.longest_recent_min": 150}
    start = date(2027, 6, 7)
    slow = {**SUB40, "details": {"distance_km": 10, "target_value": 50, "unit": "min"}}  # 32 km par semaine visés (≈ 208 min)
    with_goal = build_profile(big, [slow], start)
    capped = [s for s in plan_weeks(with_goal, start, weeks=4, start=start) if s.kind.startswith("run_")]
    per_week = {}
    for s in capped:
        per_week[s.date - timedelta(days=s.date.weekday())] = per_week.get(s.date - timedelta(days=s.date.weekday()), 0) + s.duration_min
    assert with_goal.target_volume_min == 32 * 6.5 and max(per_week.values()) <= with_goal.target_volume_min + 5
    free = build_profile(big, [], start)
    uncapped = sum(s.duration_min for s in plan_weeks(free, start, weeks=1, start=start) if s.kind.startswith("run_"))
    assert uncapped > with_goal.target_volume_min


def test_quality_sessions_follow_the_phase_and_cite_the_rule():
    strong = {**FACTS, "running.weekly_km_8w": 45, "running.weekly_km_12m": 40, "running.longest_recent_min": 90}
    seen = {}
    for day, anchor in ((date(2028, 5, 15), date(2028, 5, 1)), (date(2028, 8, 7), date(2028, 5, 1))):
        p = build_profile(strong, [SUB40], day)
        q = [s for s in plan_weeks(p, day, weeks=4, start=day, anchor=anchor) if s.kind == "run_quality"]
        assert q
        seen[q[0].details["cycle"]["macro"]] = q[0]
    assert "seuil" in seen["threshold"].details["format"] and "C11" in seen["threshold"].rules
    assert "l'allure de l'objectif" in seen["specific"].details["format"] and "C11" in seen["specific"].rules
    assert all("× 8 min" in s.details["format"] or "1 000 m" in s.details["format"] for s in seen.values())
    # paces never faster than the target pace, whatever the level
    pace = seen["specific"].details["format"].split("≈ ")[1].split("/km")[0]
    m, sec = (int(x) for x in pace.split(":"))
    assert m * 60 + sec >= 240 - 1


def test_taper_at_the_target_and_event_window_takes_precedence():
    strong = {**FACTS, "running.weekly_km_8w": 45, "running.weekly_km_12m": 40, "running.longest_recent_min": 90}
    day = RACE - timedelta(days=RACE.weekday() + 14)  # lundi, deux semaines avant la semaine de la course
    p = build_profile(strong, [SUB40], day)
    by_week = {}
    for s in plan_weeks(p, day, weeks=3, start=day, anchor=day - timedelta(weeks=60)):
        by_week.setdefault(s.date - timedelta(days=s.date.weekday()), []).append(s)
    weeks = [by_week[k] for k in sorted(by_week)]
    runs = [sum(s.duration_min for s in w if s.kind.startswith("run_")) for w in weeks]
    assert [w[0].details["cycle"]["macro"] for w in weeks] == ["specific", "taper", "race"]
    assert runs[1] < runs[0]  # C6 : le volume baisse à l'affûtage
    # un événement à moins de 12 semaines prime sur la trajectoire (C9)
    trail = {"status": "active", "kind": "event", "target_date": TODAY + timedelta(weeks=6), "priority": "principal", "title": "Trail 16 km",
             "details": {"distance_km": 16, "elevation_m": 370}}
    pe = build_profile(FACTS, [SUB40, trail], TODAY)
    macros = {s.details["cycle"]["macro"] for s in plan_weeks(pe, TODAY, weeks=4)}
    assert macros <= {"build", "peak", "taper", "race"}


def test_no_target_means_no_change_and_the_advice_follows():
    p = build_profile(FACTS, [], TODAY)
    assert p.target is None and p.level_min is None and any("Aucun objectif de course daté" in a for a in advice(p))
    assert not any("Aucun objectif de course daté" in a for a in advice(build_profile(FACTS, [SUB40], TODAY)))
    assert {s.details["cycle"]["macro"] for s in plan_weeks(p, TODAY, weeks=4)} == {"base"}


def test_cycle_projection_keeps_the_trajectory_phases():
    anchor = date(2028, 5, 1)
    monday = date(2028, 5, 8)
    cyc = cycle_for(monday, anchor, 4, None, 20, RACE)
    assert cyc.macro == "threshold" and cyc.target == RACE.isoformat()
    d = describe([{"day": date(2028, 5, 9), "details": {"cycle": cyc.as_dict()}}], date(2028, 5, 9))
    assert d["current"]["macro"] == "threshold" and d["upcoming"][-1]["phase"] == "Seuil"
    older = cycle_for(monday, anchor, 4, None).as_dict()
    for k in ("weeks_to_target", "target"):  # séances enregistrées avant la trajectoire
        older.pop(k)
    assert describe([{"day": date(2028, 5, 9), "details": {"cycle": older}}], date(2028, 5, 9))["current"]["macro"] == "base"


@pytest.fixture
def api():
    from app.auth import reset_rate_limits

    reset_rate_limits()
    repo = MemoryRepo()
    app.dependency_overrides[get_repo] = lambda: repo
    c = TestClient(app)
    uid = c.post("/auth/register", json={"name": "R", "email": "t@example.org", "password": "un-mot-de-passe-solide"}).json()["id"]
    yield c, uid
    app.dependency_overrides.clear()


def test_plan_endpoint_exposes_the_trajectory(api):
    c, uid = api
    assert c.get(f"/users/{uid}/plan").json()["trajectory"] is None
    r = c.post(f"/users/{uid}/goals", json={"title": "10 km en moins de 40 min", "kind": "performance", "priority": "principal",
                                             "target_date": (date.today() + timedelta(days=700)).isoformat(),
                                             "details": {"distance_km": 10, "target_value": 40, "unit": "min"}})
    assert r.status_code == 201
    t = c.get(f"/users/{uid}/plan").json()["trajectory"]
    assert t["target"]["time"] == "40:00" and t["verdict"] == "inconnu" and t["phases"][0]["macro"] == "base"


def test_record_only_level_is_flagged_as_a_starting_point():  # C13
    assert T.level_is_record_only({"bench.run_10k": {"pr": {"time": "45:30"}}}, 10.0) is True
    assert T.level_is_record_only({"bench.run_10k": {"pr": {"time": "45:30"}, "now": {"time": "47:00"}}}, 10.0) is False
    assert T.level_is_record_only({"sports.practiced": ["running"]}, 10.0) is False
    out = T.describe(T.pick_target([SUB40], TODAY), {"bench.run_10k": {"pr": {"time": "45:30"}}}, [SUB40], TODAY)
    assert out["level"]["record_only"] is True and out["level"]["time"] == "45:30"
