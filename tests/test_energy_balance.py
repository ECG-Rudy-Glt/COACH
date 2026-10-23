"""N11 : bilan énergétique du jour (dépense estimée face aux kcal estimées mangées), moteur puis API et contexte du coach."""
from datetime import date, timedelta

import pytest
from fastapi.testclient import TestClient

from app.auth import reset_rate_limits
from app.main import app, get_repo
from app.nutrition import engine as eng
from app.nutrition.api import coach_context
from app.repo import MemoryRepo

PW = "un-mot-de-passe-solide"
TODAY = date.today()
YESTERDAY = TODAY - timedelta(days=1)


def prof(**kw):
    return eng.NutritionProfile(sex="homme", age=30, height_cm=175, weight_kg=70, work="sédentaire", **kw)


def sess(kind="strength_upper", minutes=60, status="done", logged=None, title="Séance"):
    return {"id": 1, "kind": kind, "title": title, "duration_min": minutes, "status": status, "logged": logged}


def test_base_is_bmr_times_activity_level_and_sessions_use_met_minus_one():
    p = prof()
    bmr = eng.bmr_mifflin("homme", 70, 175, 30)
    e = eng.day_expenditure(p, [sess(minutes=60)], [])
    assert e["base_kcal"] == round(bmr * 1.25) and e["activity_kcal"] == round((4.0 - 1) * 70) and not e["partial"] and e["rules"] == ["N11"]
    assert e["so_far_kcal"] == e["base_kcal"] + 210 == e["projected_kcal"]


def test_activity_with_calories_keeps_only_the_active_part_and_a_linked_session_is_counted_once():
    p = prof()
    bmr = eng.bmr_mifflin("homme", 70, 175, 30)
    act = {"garmin_id": "g1", "sport": "run", "duration_s": 3600, "calories": 600, "name": "Footing"}
    linked = sess("run_easy", 55, logged={"garmin_id": "g1"})
    e = eng.day_expenditure(p, [linked], [act])
    assert len(e["items"]) == 1 and e["items"][0]["source"] == "watch" and e["activity_kcal"] == round(600 - bmr / 24)  # pas de double comptage
    no_cal = eng.day_expenditure(p, [], [{"garmin_id": "g2", "sport": "run", "duration_s": 3600, "calories": None}])
    assert no_cal["items"][0]["source"] == "met" and no_cal["activity_kcal"] == round((8.0 - 1) * 70)


def test_skipped_and_planned_sessions_are_not_spent_but_remaining_ones_are_projected():
    e = eng.day_expenditure(prof(), [sess(status="skipped"), sess("run_easy", 40, status="planned")], [], elapsed=0.5)
    assert e["activity_kcal"] == 0 and e["partial"] and e["so_far_kcal"] == round(e["base_kcal"] * 0.5)
    assert e["planned_remaining_kcal"] == round(7 * 70 * 40 / 60) and e["projected_kcal"] == e["base_kcal"] + e["planned_remaining_kcal"]
    assert eng.day_expenditure(prof(), [sess("run_easy", 40, status="planned")], [], planned=False)["planned_remaining_kcal"] == 0


def test_balance_is_approximate_and_never_shown_for_protected_profiles_or_without_meals():
    spent = eng.day_expenditure(prof(), [], [])
    assert eng.day_balance(prof(), spent, 2000, 3)["kcal"] == 2000 - spent["so_far_kcal"]
    assert eng.day_balance(prof(), spent, 0, 0) == {"kcal": None, "reason": "no_meals"}
    assert eng.day_balance(prof(blocked_reason="N7"), spent, 1200, 3) == {"kcal": None, "reason": "protected"}  # N7 : jamais de solde déficitaire affiché


@pytest.fixture
def ctx():
    reset_rate_limits()
    repo = MemoryRepo()
    app.dependency_overrides[get_repo] = lambda: repo
    c = TestClient(app)
    uid = c.post("/auth/register", json={"name": "R", "email": "e@example.org", "password": PW}).json()["id"]
    for q, v in [("body.height", 175), ("body.weight", 70), ("body.birth_year", 1995), ("body.sex", "homme"), ("goal.weight_direction", "perdre")]:
        c.post(f"/users/{uid}/answers", json={"question_id": q, "value": v})
    yield c, uid, repo
    app.dependency_overrides.clear()


def meal(repo, uid, day, kcal):
    m = repo.add_meal(uid, day, "déjeuner", "repas", None)
    repo.set_meal_analysis(uid, m["id"], {"kcal": kcal, "protein_g": 30, "carbs_g": 60, "fat_g": 20})


def add_done(c, uid, day, kind="run_easy", minutes=50):
    return c.post(f"/users/{uid}/plan/sessions", json={"day": day.isoformat(), "kind": kind, "title": "", "duration_min": minutes}).json()


def test_api_day_energy_counts_manual_session_and_meals_and_keeps_the_target(ctx):
    c, uid, repo = ctx
    before = c.get(f"/users/{uid}/nutrition/day", params={"day": YESTERDAY.isoformat()}).json()
    add_done(c, uid, YESTERDAY, "sport_bike", 60)
    meal(repo, uid, YESTERDAY, 2100)
    d = c.get(f"/users/{uid}/nutrition/day", params={"day": YESTERDAY.isoformat()}).json()
    e = d["energy"]
    assert e["spent"]["activity_kcal"] == round(6.0 * 70) and e["spent"]["items"][0]["source"] == "met" and not e["current"]
    assert e["eaten_kcal"] == 2100 and e["balance"]["kcal"] == 2100 - e["spent"]["so_far_kcal"] and not e["protected"]
    assert d["targets"]["day_load"] == "training" and 110 <= d["targets"]["kcal"] - before["targets"]["kcal"] <= 130  # seul N3 (±120 kcal selon la charge) : la dépense ne relève pas la cible


def test_api_today_is_partial_and_future_has_no_balance(ctx):
    c, uid, repo = ctx
    e = c.get(f"/users/{uid}/nutrition/day").json()["energy"]
    assert e["current"] and e["balance"]["reason"] == "no_meals" and e["spent"]["so_far_kcal"] <= e["spent"]["projected_kcal"]
    tomorrow = c.get(f"/users/{uid}/nutrition/day", params={"day": (TODAY + timedelta(days=1)).isoformat()}).json()["energy"]
    assert tomorrow["future"] and tomorrow["balance"] == {"kcal": None, "reason": "future"}


def test_api_protected_profile_gets_no_balance(ctx):
    c, uid, repo = ctx
    c.post(f"/users/{uid}/answers", json={"question_id": "body.birth_year", "value": TODAY.year - 15})
    meal(repo, uid, YESTERDAY, 1800)
    e = c.get(f"/users/{uid}/nutrition/day", params={"day": YESTERDAY.isoformat()}).json()["energy"]
    assert e["protected"] and e["balance"] == {"kcal": None, "reason": "protected"}


def test_coach_context_reuses_the_same_figures(ctx):
    c, uid, repo = ctx
    add_done(c, uid, TODAY, "run_easy", 50)
    meal(repo, uid, TODAY, 900)
    api = c.get(f"/users/{uid}/nutrition/day").json()["energy"]
    ctxt = coach_context(repo, uid, TODAY)["bilan_energetique_jour"]
    assert ctxt["depense_prevue_journee_kcal"] == api["spent"]["projected_kcal"] and ctxt["dont_activites_faites_kcal"] == api["spent"]["activity_kcal"]
    assert ctxt["mange_estime_kcal"] == 900 and "N11" in ctxt["regle"] and ctxt["activites"][0]["source"] == "MET"
