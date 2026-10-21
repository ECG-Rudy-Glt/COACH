"""Écran Statistiques, lot « Quotidien » : règles ST1 à ST5."""
from datetime import date, datetime, timedelta

import pytest
from fastapi.testclient import TestClient

from app.garmin import client as gc
from app.main import app, get_repo
from app.repo import MemoryRepo
from app.stats import daily

PW = "un-mot-de-passe-solide"
TODAY = date(2026, 10, 21)  # un mercredi


def meal(day, kcal=None, protein=0):
    return {"day": day, "analysis": {"kcal": kcal, "protein_g": protein} if kcal is not None else None}


def act(gid, day, sport="run", km=8.0, minutes=48, name="Sortie"):
    return {"garmin_id": gid, "day": day, "started_at": datetime(day.year, day.month, day.day, 7), "sport": sport, "type_key": "running", "name": name,
            "duration_s": minutes * 60, "distance_m": km * 1000, "elevation_m": 0.0, "avg_hr": 150, "max_hr": 170, "calories": 500, "training_load": 80.0}


# ---- Garmin : relevé des pas ----

def test_parse_steps_keeps_real_days_and_drops_zero_and_junk():
    rows = gc.parse_steps([{"calendarDate": "2026-10-20", "totalSteps": 8123}, {"calendarDate": "2026-10-19", "totalSteps": 0},
                           {"calendarDate": "n'importe quoi", "totalSteps": 5}, {"calendarDate": "2026-10-18"}, "x", None])
    assert rows == [{"day": date(2026, 10, 20), "metric": "steps", "value": 8123.0}]
    assert gc.parse_steps(None) == []


def test_fetch_steps_splits_in_28_day_chunks_and_keeps_what_it_received(monkeypatch):
    monkeypatch.setattr(gc.time, "sleep", lambda s: None)

    class Client:
        def __init__(self, fail_on=None):
            self.calls, self.fail_on = [], fail_on

        def get_daily_steps(self, a, b):
            self.calls.append((a, b))
            if len(self.calls) == self.fail_on:
                raise KeyError("boom")
            return [{"calendarDate": a, "totalSteps": 1000}]

    c = Client()
    rows = gc.fetch_steps(c, date(2026, 8, 1), date(2026, 10, 1), (KeyError,))
    assert len(c.calls) == 3 and c.calls[0] == ("2026-08-01", "2026-08-28") and c.calls[1][0] == "2026-08-29" and len(rows) == 3
    partial = gc.fetch_steps(Client(fail_on=2), date(2026, 8, 1), date(2026, 10, 1), (KeyError,))
    assert len(partial) == 1  # la première tranche est conservée


# ---- ST4 : pas ----

def test_st4_steps_today_is_shown_but_not_averaged_and_missing_days_stay_missing():
    rows = [{"day": TODAY - timedelta(days=i), "metric": "steps", "value": v} for i, v in [(0, 2000.0), (1, 9000.0), (3, 7000.0)]]
    b = daily.steps_block(rows, TODAY, True)
    assert len(b["days"]) == 7 and b["days"][-1] == {"day": "2026-10-21", "steps": 2000}
    assert b["average"] == 8000 and b["days_measured"] == 2 and b["today_partial"] is True
    assert [x["steps"] for x in b["days"]].count(None) == 4  # ST1 : jamais 0 à la place d'une donnée absente
    empty = daily.steps_block([], TODAY, False)
    assert empty["average"] is None and empty["connected"] is False


# ---- ST2 : repas face aux cibles ----

def test_st2_average_only_over_estimated_days_and_no_target_without_profile():
    meals = [meal(TODAY, 2000, 120), meal(TODAY, 500, 20), meal(TODAY - timedelta(days=1), None), meal(TODAY - timedelta(days=2), 1800, 100)]
    tg = {TODAY - timedelta(days=i): {"kcal": 2000, "protein_g": 130} for i in range(7)}
    b = daily.nutrition_block(meals, TODAY, tg)
    by = {d["day"]: d for d in b["days"]}
    assert by["2026-10-21"]["kcal"] == 2500 and by["2026-10-21"]["estimated_meals"] == 2
    assert by["2026-10-20"]["kcal"] is None and by["2026-10-20"]["meals"] == 1  # repas sans estimation : pas de valeur, pas un zéro
    assert b["average"] == {"kcal": 2150, "protein_g": 120, "target_kcal": 2000, "target_protein_g": 130, "days": 2}
    no_target = daily.nutrition_block(meals, TODAY, None)
    assert no_target["has_target"] is False and no_target["average"]["target_kcal"] is None and no_target["days"][0]["target_kcal"] is None
    assert daily.nutrition_block([], TODAY, tg)["average"] is None


# ---- ST3 : poids ----

def test_st3_weight_block_keeps_the_trend_series():
    trend = {"series": [{"day": f"2026-09-{i:02d}", "kg": 70.0, "avg": 70.0} for i in range(1, 29)] * 3, "current": 70.0, "rate_pct_per_week": None}
    b = daily.weight_block(trend, 65.0)
    assert len(b["series"]) == 60 and b["target_kg"] == 65.0 and b["rate_pct_per_week"] is None
    assert daily.weight_block({"series": [], "current": None, "rate_pct_per_week": None}, None)["series"] == []


# ---- ST5 : activité ----

def test_st5_a_linked_session_is_counted_once_and_pace_needs_a_real_run():
    acts = [act("1", TODAY - timedelta(days=1)), act("2", TODAY - timedelta(days=2), km=0.4, minutes=5, name="Échauffement"), act("3", TODAY - timedelta(days=3), sport="strength", km=0, minutes=40)]
    sessions = [{"id": 1, "day": TODAY - timedelta(days=1), "kind": "run_easy", "title": "Footing", "duration_min": 50, "status": "done", "logged": {"garmin_id": "1", "minutes": 48}},
                {"id": 2, "day": TODAY - timedelta(days=4), "kind": "strength_upper", "title": "Haut du corps", "duration_min": 55, "status": "done", "logged": {"minutes": 50}},
                {"id": 3, "day": TODAY - timedelta(days=5), "kind": "run_easy", "title": "Manquée", "duration_min": 40, "status": "skipped", "logged": None}]
    items = daily.recent_items(acts, sessions, TODAY)
    assert [i["source"] for i in items] == ["montre", "montre", "montre", "saisie"] and sum(1 for i in items if i["title"] == "Footing") == 0
    run = next(i for i in items if i["title"] == "Sortie")
    assert run["pace_min_km"] == 6.0 and next(i for i in items if i["title"] == "Échauffement")["pace_min_km"] is None
    assert next(i for i in items if i["source"] == "saisie")["minutes"] == 50
    wk = daily.week_block(sessions, acts, TODAY)  # semaine du lundi 19 octobre
    assert wk["monday"] == "2026-10-19" and wk["planned"] == 1 and wk["done"] == 1 and wk["run_km"] == 8.4 and wk["minutes"] == 48 + 5
    assert daily.recent_items([], [], TODAY) == []


# ---- API ----

@pytest.fixture
def ctx():
    from app.auth import reset_rate_limits

    reset_rate_limits()
    repo = MemoryRepo()
    app.dependency_overrides[get_repo] = lambda: repo
    c = TestClient(app)
    uid = c.post("/auth/register", json={"name": "R", "email": "st@example.org", "password": PW}).json()["id"]
    yield c, uid, repo
    app.dependency_overrides.clear()


def test_daily_api_requires_the_right_user(ctx):
    c, uid, _ = ctx
    other = c.post("/auth/register", json={"name": "E", "email": "st2@example.org", "password": PW}).json()["id"]
    assert c.get(f"/users/{uid}/stats/daily").status_code == 403  # connecté en tant qu'autre utilisateur
    assert c.get(f"/users/{other}/stats/daily").status_code == 200
    c.post("/auth/logout")
    assert c.get(f"/users/{other}/stats/daily").status_code == 401


def test_daily_api_with_no_data_says_so_instead_of_inventing(ctx):
    c, uid, _ = ctx
    d = c.get(f"/users/{uid}/stats/daily").json()
    assert d["steps"]["connected"] is False and d["steps"]["average"] is None and d["nutrition"]["has_target"] is False and d["nutrition"]["average"] is None
    assert d["weight"]["series"] == [] and d["weight"]["current"] is None and d["recent"] == [] and d["week"]["done"] == 0


def test_daily_api_with_data(ctx):
    c, uid, repo = ctx
    for q, v in [("body.height", 159), ("body.weight", 67), ("body.birth_year", 2001), ("body.sex", "homme"), ("goal.weight_direction", "perdre")]:
        c.post(f"/users/{uid}/answers", json={"question_id": q, "value": v})
    today = date.today()
    repo.upsert_metrics(uid, [{"day": today - timedelta(days=1), "metric": "steps", "value": 9500.0}])
    repo.save_garmin(uid, "g@example.org", "enc")
    m = repo.add_meal(uid, today - timedelta(days=1), "déjeuner", "riz", None)
    repo.set_meal_analysis(uid, m["id"], {"kcal": 700, "protein_g": 40, "carbs_g": 80, "fat_g": 20})
    repo.upsert_weight(uid, today, 66.5, None)
    repo.upsert_activities(uid, [act("9", today - timedelta(days=2))])
    d = c.get(f"/users/{uid}/stats/daily").json()
    assert d["steps"]["connected"] is True and d["steps"]["average"] == 9500
    n = d["nutrition"]
    assert n["has_target"] is True and n["average"]["kcal"] == 700 and n["average"]["target_kcal"] > 1200 and n["days"][-2]["kcal"] == 700
    assert d["weight"]["current"] == 66.5 and d["recent"][0]["sport"] == "run" and d["recent"][0]["pace_min_km"] == 6.0
