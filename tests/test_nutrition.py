import base64
from datetime import date, timedelta

import pytest
from fastapi.testclient import TestClient

from app.coach.llm import LLMError, LLMResult
from app.main import app, get_repo
from app.nutrition import analyze as nut_analyze
from app.nutrition import engine as eng
from app.repo import MemoryRepo

PW = "un-mot-de-passe-solide"
TODAY = date.today()
JPEG = base64.b64encode(b"\xff\xd8\xff\xe0" + b"0" * 200).decode()
FACTS = {"body.sex_for_calc": "homme", "body.birth_year": 2001, "body.height_cm": 159, "body.weight_kg": 67, "goal.weight_direction": "perdre",
         "constraints.work_activity": "sédentaire", "goal.target_weight_kg": 60}


def test_bmr_and_targets_for_the_reference_profile():
    assert round(eng.bmr_mifflin("homme", 67, 159, 25)) == 1544
    p = eng.build_profile(FACTS, date(2026, 10, 18), None, [], None)
    tg = eng.targets(p)
    assert tg["protein_g"] == 134 and tg["fat_g"] == 54 and tg["rate_pct_per_week"] == 0.75
    assert tg["kcal"] >= max(tg["bmr"], 1500) and tg["deficit_kcal"] > 300 and tg["carbs_g"] > 100
    near = eng.build_profile(FACTS, date(2026, 10, 18), None, [], 7)
    assert eng.targets(near)["rate_pct_per_week"] == 0.5 and eng.targets(near)["kcal"] > tg["kcal"]  # près d'un objectif : déficit plus doux


def test_floor_safety_and_training_day_shift():
    p = eng.build_profile({**FACTS, "body.weight_kg": 45, "body.height_cm": 150}, date(2026, 10, 18), None, [], None)
    tg = eng.targets(p)
    assert tg["kcal"] >= 1500 and tg["floor_applied"] is True and "plancher" in tg["notice"]
    assert eng.targets(p, "rest")["kcal"] >= eng.targets(p)["bmr"]  # jamais sous le métabolisme de base, même un jour de repos
    free = eng.build_profile({**FACTS, "constraints.work_activity": "physique"}, date(2026, 10, 18), None, [], None)
    assert eng.targets(free, "training")["kcal"] - eng.targets(free, "rest")["kcal"] == 240
    for cond in ("trouble alimentaire passé", "grossesse ou post-partum"):
        b = eng.build_profile({**FACTS, "health.conditions": [cond]}, date(2026, 10, 18), None, [], None)
        t = eng.targets(b)
        assert t["rate_pct_per_week"] == 0 and t["deficit_kcal"] == 0 and "N7" in t["notice"]
    minor = eng.build_profile({**FACTS, "body.birth_year": 2012}, date(2026, 10, 18), None, [], None)
    assert eng.targets(minor)["deficit_kcal"] == 0


def test_training_sessions_raise_the_energy_target():
    base = eng.targets(eng.build_profile(FACTS, date(2026, 10, 18), None, [], None))["tdee"]
    sessions = [{"kind": "run_long", "duration_min": 60}, {"kind": "strength_upper", "duration_min": 60}]
    assert eng.targets(eng.build_profile(FACTS, date(2026, 10, 18), None, sessions, None))["tdee"] > base + 80


def test_weight_trend_uses_a_moving_average_and_advises():
    e = [{"day": TODAY - timedelta(days=21 - 3 * i), "kg": 67 - 0.3 * i + (0.8 if i == 3 else 0)} for i in range(8)]
    tr = eng.trend(e, TODAY)
    assert tr["rate_pct_per_week"] is not None and tr["rate_pct_per_week"] < 0 and tr["series"][-1]["avg"] > tr["series"][-1]["kg"] - 1
    p = eng.build_profile(FACTS, TODAY, None, [], None)
    adv = eng.advice(p, eng.targets(p), {"rate_pct_per_week": -0.1, "current": 66}, 14)
    assert any("100 à 150 kcal" in a for a in adv)
    assert any("trop" in a or "rapide" in a for a in eng.advice(p, eng.targets(p), {"rate_pct_per_week": -1.4, "current": 66}, 14))
    assert any("Pesez-vous" in a for a in eng.advice(p, eng.targets(p), {"rate_pct_per_week": None}, 0))


def test_analysis_validation_clips_and_recomputes_inconsistent_energy():
    out = nut_analyze.validate({"totals": {"kcal_min": 100, "kcal_max": 120, "protein_g": 40, "carbs_g": 60, "fat_g": 20}, "confidence": "bizarre",
                                "items": [{"name": "riz", "kcal": 99999}] * 20})
    assert out["confidence"] == "faible" and out["note"] and 500 < out["kcal"] < 800 and len(out["items"]) == 12 and out["items"][0]["kcal"] == nut_analyze.MAX_KCAL_MEAL
    assert nut_analyze.validate({"totals": {"kcal_min": 900, "kcal_max": 300}})["kcal_min"] == 300


class FakeLLM:
    def __init__(self):
        self.calls = []
        self.fail = False

    def complete(self, system, user, max_tokens, model=None, history=None, image=None, json_mode=False):
        self.calls.append((user, bool(image)))
        if self.fail:
            raise LLMError("Le service IA est injoignable.")
        return LLMResult('{"items":[{"name":"poulet riz","quantity":"1 assiette","kcal":650,"protein_g":45,"carbs_g":70,"fat_g":18}],'
                         '"totals":{"kcal_min":550,"kcal_max":750,"protein_g":45,"carbs_g":70,"fat_g":18},"confidence":"moyenne",'
                         '"assumptions":"portion standard","feedback":"Repas équilibré.","tips":["Ajoutez des légumes."]}', 900, 300, model or "m")


@pytest.fixture
def ctx(tmp_path, monkeypatch):
    from app.auth import reset_rate_limits

    reset_rate_limits()
    monkeypatch.setenv("MEDIA_DIR", str(tmp_path))
    repo, llm = MemoryRepo(), FakeLLM()
    app.dependency_overrides[get_repo] = lambda: repo
    old = app.state.llm
    app.state.llm = llm
    c = TestClient(app)
    uid = c.post("/auth/register", json={"name": "R", "email": "n@example.org", "password": PW}).json()["id"]
    for q, v in [("body.height", 159), ("body.weight", 67), ("body.birth_year", 2001), ("body.sex", "homme"), ("goal.weight_direction", "perdre")]:
        c.post(f"/users/{uid}/answers", json={"question_id": q, "value": v})
    yield c, uid, repo, llm
    app.state.llm = old
    app.dependency_overrides.clear()


def test_meal_with_photo_is_estimated_stored_and_summed(ctx, tmp_path):
    c, uid, repo, llm = ctx
    r = c.post(f"/users/{uid}/nutrition/meals", json={"slot": "déjeuner", "description": "poulet et riz", "photo_b64": JPEG})
    assert r.status_code == 201 and r.json()["analysis_error"] is None
    m = r.json()["meal"]
    assert m["has_photo"] and m["analysis"]["kcal"] == 650 and m["analysis"]["estimated"] is True
    assert llm.calls[0][1] is True  # la photo est transmise à l'IA
    assert c.get(f"/users/{uid}/nutrition/meals/{m['id']}/photo").status_code == 200
    day = c.get(f"/users/{uid}/nutrition/day").json()
    assert day["totals"]["kcal"] == 650 and day["remaining"]["kcal"] == day["targets"]["kcal"] - 650 and day["targets"]["protein_g"] == 134
    assert c.delete(f"/users/{uid}/nutrition/meals/{m['id']}").json() == {"ok": True}
    assert not list((tmp_path / "meals" / str(uid)).glob("*"))  # la photo est supprimée avec le repas
    assert c.get(f"/users/{uid}/nutrition/day").json()["meals"] == []


def test_validation_limits_and_failures_keep_the_meal(ctx):
    c, uid, repo, llm = ctx
    url = f"/users/{uid}/nutrition/meals"
    assert c.post(url, json={"slot": "déjeuner", "description": ""}).status_code == 422
    assert c.post(url, json={"slot": "brunch", "description": "x"}).status_code == 422
    assert c.post(url, json={"slot": "déjeuner", "photo_b64": base64.b64encode(b"MZ" + b"0" * 50).decode()}).status_code == 422  # pas une image
    assert c.post(url, json={"slot": "déjeuner", "description": "x", "photo_b64": "pas-du-base64!!"}).status_code == 422
    assert c.post(url, json={"slot": "dîner", "description": "x", "day": str(TODAY - timedelta(days=30))}).status_code == 422
    llm.fail = True
    r = c.post(url, json={"slot": "dîner", "description": "pâtes"})
    assert r.status_code == 201 and "injoignable" in r.json()["analysis_error"] and r.json()["meal"]["analysis"] is None
    llm.fail = False
    mid = r.json()["meal"]["id"]
    assert c.post(f"/users/{uid}/nutrition/meals/{mid}/estimate").json()["analysis"]["kcal"] == 650
    assert c.post(f"/users/{uid}/nutrition/meals/999/estimate").status_code == 404


def test_other_users_cannot_see_meals_or_photos(ctx):
    c, uid, repo, llm = ctx
    mid = c.post(f"/users/{uid}/nutrition/meals", json={"slot": "déjeuner", "description": "x", "photo_b64": JPEG}).json()["meal"]["id"]
    c.post("/auth/logout")
    other = c.post("/auth/register", json={"name": "E", "email": "e3@example.org", "password": PW}).json()["id"]
    assert c.get(f"/users/{uid}/nutrition/day").status_code == 403
    assert c.get(f"/users/{other}/nutrition/meals/{mid}/photo").status_code == 404
    assert c.delete(f"/users/{other}/nutrition/meals/{mid}").status_code == 404


def test_weight_and_progress(ctx):
    c, uid, repo, llm = ctx
    for i in range(8):
        r = c.post(f"/users/{uid}/nutrition/weight", json={"day": str(TODAY - timedelta(days=21 - 3 * i)), "kg": 68 - 0.25 * i, "waist_cm": 80})
        assert r.status_code == 200
    assert c.post(f"/users/{uid}/nutrition/weight", json={"kg": 10}).status_code == 422
    p = c.get(f"/users/{uid}/nutrition/progress").json()
    assert p["profile"]["bmi"] > 20 and p["trend"]["rate_pct_per_week"] < 0 and len(p["weights"]) == 8 and p["advice"] and "disclaimer" in p
    assert p["profile"]["weight_kg"] == pytest.approx(68 - 0.25 * 7)  # le dernier poids saisi pilote les cibles


def test_lunchbox_prepared_today_is_counted_tomorrow_at_lunch(ctx):
    c, uid, repo, llm = ctx
    r = c.post(f"/users/{uid}/nutrition/meals", json={"slot": "dîner", "description": "bourguignon", "for_tomorrow": True})
    assert r.status_code == 201
    m = r.json()["meal"]
    tomorrow = (TODAY + timedelta(days=1)).isoformat()
    assert m["day"] == tomorrow and m["slot"] == "déjeuner" and m["analysis"]["kcal"] == 650
    assert c.get(f"/users/{uid}/nutrition/day").json()["totals"]["kcal"] == 0
    assert c.get(f"/users/{uid}/nutrition/day?day={tomorrow}").json()["totals"]["kcal"] == 650
    # depuis demain, « pour demain » viserait après-demain : refusé
    assert c.post(f"/users/{uid}/nutrition/meals", json={"day": tomorrow, "slot": "dîner", "description": "x", "for_tomorrow": True}).status_code == 422


def test_big_portion_is_passed_to_the_estimator(ctx):
    c, uid, repo, llm = ctx
    r = c.post(f"/users/{uid}/nutrition/meals", json={"slot": "dîner", "description": "pâtes carbonara", "portion": "grosse"})
    assert r.status_code == 201 and "grosse" in r.json()["meal"]["description"] and "grosse" in llm.calls[0][0]
    assert "sous-évalue" in nut_analyze.SYSTEM
