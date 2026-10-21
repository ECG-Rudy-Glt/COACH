import base64
import json
from datetime import date, timedelta

import pytest
from fastapi.testclient import TestClient

from app.coach.llm import LLMError, LLMResult
from app.main import app, get_repo
from app.nutrition import analyze as nut_analyze
from app.nutrition import barcode
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


def test_estimator_prompt_asks_for_high_estimates_and_uses_the_weight():
    assert "sous-évalue" in nut_analyze.SYSTEM and "poids × densité" in nut_analyze.SYSTEM and "bourguignon" in nut_analyze.SYSTEM


# ---- réponses enregistrées des fournisseurs : le schéma des estimations (#34, #55) ----
from pathlib import Path  # noqa: E402

from app.coach import llm as llm_mod  # noqa: E402

FIXTURES = Path(__file__).parent / "fixtures" / "llm"


@pytest.mark.parametrize("provider,fixture", [("openai", "openai_chat_meal.json"), ("ollama", "ollama_chat_meal.json"), ("anthropic", "anthropic_messages_meal.json")])
def test_recorded_provider_replies_yield_a_valid_meal_schema(monkeypatch, provider, fixture):
    monkeypatch.setenv("LLM_PROVIDER", provider)
    monkeypatch.setenv("LLM_API_KEY", "k")
    for k in ("LLM_JSON_MODE", "LLM_TOOLS", "LLM_MODEL", "LLM_BASE_URL"):
        monkeypatch.delenv(k, raising=False)
    monkeypatch.setattr(llm_mod, "_http_json", lambda url, body, headers: json.loads((FIXTURES / fixture).read_text(encoding="utf-8")))
    llm = llm_mod.AnthropicLLM() if provider == "anthropic" else llm_mod.OpenAICompatLLM(provider)
    out, usage = nut_analyze.analyze(llm, "pâtes à la crème", None, "m")
    assert out["confidence"] == "faible" and out["kcal_min"] == 600 and out["kcal_max"] == 900 and out["kcal"] == 750 and usage["in"] > 0
    assert len(out["questions"]) == nut_analyze.MAX_QUESTIONS and out["questions"][0]["choices"] == ["moins de 250 g", "250 à 400 g", "plus de 400 g"]
    assert out["items"][0]["name"] == "pâtes à la crème" and set(out) >= {"kcal", "protein_g", "carbs_g", "fat_g", "tips", "feedback", "assumptions"}


def test_questions_are_bounded_and_dropped_when_confident_or_not_asked():
    raw = {"totals": {"kcal_min": 500, "kcal_max": 700, "protein_g": 30, "carbs_g": 60, "fat_g": 20}, "confidence": "faible",
           "questions": [{"text": "x" * 500, "choices": ["a" * 100, "b", "c", "d", "e"]}, {"text": ""}, "pas un objet", {"text": "Sauce ?"}, {"text": "Trop"}]}
    qs = nut_analyze.validate(raw)["questions"]
    assert [q["id"] for q in qs] == [1, 2] and len(qs[0]["text"]) == 160 and len(qs[0]["choices"]) == 4 and len(qs[0]["choices"][0]) == 40 and qs[1]["choices"] == []
    assert nut_analyze.validate({**raw, "confidence": "élevée"})["questions"] == []  # sûr de lui : rien à demander
    assert nut_analyze.validate(raw, ask=False)["questions"] == []
    assert nut_analyze.validate({**raw, "questions": "oui"})["questions"] == []


class AskingLLM(FakeLLM):
    """Première passe : confiance faible et deux questions ; avec des réponses : estimation affinée sans question."""

    def complete(self, system, user, max_tokens, model=None, history=None, image=None, json_mode=False):
        self.calls.append((user, bool(image)))
        asked = json.loads(user)
        if asked.get("reponses"):
            kcal = 900
            body = {"confidence": "moyenne", "questions": [{"text": "Encore ?"}]}  # le serveur ignore toute question après des réponses
        else:
            kcal, body = 600, {"confidence": "faible", "questions": [{"text": "Quel poids ?", "choices": ["150 g", "300 g"]}, {"text": "Huile ?", "choices": ["oui", "non"]}, {"text": "Boisson ?"}]}
        body["totals"] = {"kcal_min": kcal - 100, "kcal_max": kcal + 100, "protein_g": 30, "carbs_g": round((kcal - 270 - 120) / 4), "fat_g": 30}
        return LLMResult(json.dumps(body), 900, 300, model or "m")


def test_clarifying_questions_are_returned_answered_and_skippable(ctx):
    c, uid, repo, _ = ctx
    llm = AskingLLM()
    app.state.llm = llm
    url = f"/users/{uid}/nutrition"
    m = c.post(f"{url}/meals", json={"slot": "déjeuner", "description": "pâtes à la crème"}).json()["meal"]
    assert m["analysis"]["kcal"] == 600 and [q["text"] for q in m["analysis"]["questions"]] == ["Quel poids ?", "Huile ?"]  # 2 questions au plus
    assert json.loads(llm.calls[0][0])["poser_des_questions"] is True
    r = c.post(f"{url}/meals/{m['id']}/estimate", json={"answers": [{"question": "Quel poids ?", "answer": "300 g"}, {"question": "Huile ?", "answer": ""}]})
    assert r.status_code == 200 and r.json()["analysis"]["kcal"] == 900 and r.json()["analysis"]["questions"] == []
    sent = json.loads(llm.calls[1][0])
    assert sent["reponses"] == [{"question": "Quel poids ?", "reponse": "300 g"}] and sent["poser_des_questions"] is False  # réponse vide ignorée
    assert c.get(f"{url}/day").json()["totals"]["kcal"] == 900
    # passer : on garde l'estimation de départ, sans nouvel appel à l'IA
    m2 = c.post(f"{url}/meals", json={"slot": "dîner", "description": "gratin"}).json()["meal"]
    n = len(llm.calls)
    r = c.post(f"{url}/meals/{m2['id']}/estimate", json={"skip": True}).json()
    assert r["analysis"]["kcal"] == 600 and r["analysis"]["questions"] == [] and len(llm.calls) == n
    # l'utilisateur peut refuser les questions d'emblée
    m3 = c.post(f"{url}/meals", json={"slot": "collation", "description": "yaourt", "clarify": False}).json()["meal"]
    assert m3["analysis"]["questions"] == [] and json.loads(llm.calls[-1][0])["poser_des_questions"] is False
    assert c.post(f"{url}/meals/{m['id']}/estimate", json={"answers": [{"question": "q", "answer": "x" * 300}]}).status_code == 422
    assert c.post(f"{url}/meals/{m['id']}/estimate", json={"answers": [{"question": "q", "answer": "a"}] * 3}).status_code == 422
    assert c.post(f"{url}/meals/999/estimate", json={"skip": True}).status_code == 404


OFF_SAMPLE = {"status": 1, "code": "3017620422003", "product": {"product_name": "Pâte à tartiner  noisettes", "brands": "Marque, Autre", "serving_quantity": "15",
              "nutriments": {"energy-kcal_100g": 539, "proteins_100g": 6.3, "carbohydrates_100g": 57.5, "fat_100g": 30.9}}}


def test_barcode_checksum_and_parsing():
    assert barcode.valid_code("3017620422003") and barcode.valid_code("96385074") and not barcode.valid_code("3017620422004") and not barcode.valid_code("12345") and not barcode.valid_code("abcdefgh")
    p = barcode.parse_product(OFF_SAMPLE)
    assert p and p["name"] == "Pâte à tartiner noisettes" and p["brand"] == "Marque" and p["kcal_100g"] == 539 and p["serving_g"] == 15
    kj = barcode.parse_product({"status": 1, "product": {"nutriments": {"energy_100g": 1000}}})
    assert kj and kj["kcal_100g"] == pytest.approx(239, abs=1) and kj["name"] == "Produit emballé"
    assert barcode.parse_product({"status": 0}) is None and barcode.parse_product({"status": 1, "product": {"nutriments": {}}}) is None
    a = barcode.analysis_for(p, 30)
    assert a["kcal"] == 162 and a["protein_g"] == 2 and a["carbs_g"] == 17 and a["fat_g"] == 9 and a["estimated"] is False and a["source"] == "openfoodfacts"


def test_barcode_request_is_minimal_and_respects_the_switch(monkeypatch):
    seen = []

    def fake(url):
        seen.append(url)
        return OFF_SAMPLE

    monkeypatch.setattr(barcode, "_get_json", fake)
    monkeypatch.delenv("OFF_ENABLED", raising=False)
    monkeypatch.delenv("OFF_BASE_URL", raising=False)
    assert barcode.lookup("3017620422003")["name"].startswith("Pâte")
    assert seen == ["https://world.openfoodfacts.org/api/v2/product/3017620422003.json?fields=" + barcode.FIELDS]  # seul le code quitte le serveur
    assert "COACH" in barcode.USER_AGENT and "@" not in barcode.USER_AGENT
    monkeypatch.setenv("OFF_ENABLED", "0")
    with pytest.raises(barcode.BarcodeError) as e:
        barcode.lookup("3017620422003")
    assert e.value.status == 503 and len(seen) == 1
    monkeypatch.setenv("OFF_ENABLED", "1")
    monkeypatch.setenv("OFF_BASE_URL", "file:///etc")
    with pytest.raises(barcode.BarcodeError):
        barcode.lookup("3017620422003")


def test_barcode_http_errors_are_translated(monkeypatch):
    import io
    import urllib.error

    def boom(*a, **k):
        raise urllib.error.URLError("down")

    monkeypatch.setattr(barcode.urllib.request, "urlopen", boom)
    with pytest.raises(barcode.BarcodeError, match="injoignable"):
        barcode._get_json("https://world.openfoodfacts.org/x")

    def nf(*a, **k):
        raise urllib.error.HTTPError("u", 404, "nf", {}, io.BytesIO(b""))  # type: ignore[arg-type]

    monkeypatch.setattr(barcode.urllib.request, "urlopen", nf)
    assert barcode._get_json("https://world.openfoodfacts.org/x") == {"status": 0}


def test_meal_from_a_barcode_uses_the_package_values_without_ai(ctx, monkeypatch):
    c, uid, repo, llm = ctx
    monkeypatch.setattr(barcode, "_get_json", lambda url: OFF_SAMPLE)
    monkeypatch.delenv("OFF_ENABLED", raising=False)
    url = f"/users/{uid}/nutrition"
    assert c.get(f"{url}/barcode/3017620422003").json()["serving_g"] == 15
    assert c.get(f"{url}/barcode/3017620422004").status_code == 422
    r = c.post(f"{url}/meals", json={"slot": "collation", "barcode": "3017620422003", "grams": 30})
    assert r.status_code == 201 and r.json()["meal"]["analysis"]["kcal"] == 162 and r.json()["meal"]["analysis"]["source"] == "openfoodfacts"
    assert "30 g" in r.json()["meal"]["description"] and llm.calls == []
    assert c.post(f"{url}/meals", json={"slot": "collation", "barcode": "3017620422003"}).status_code == 422  # quantité obligatoire
    monkeypatch.setattr(barcode, "_get_json", lambda url: {"status": 0})
    assert c.post(f"{url}/meals", json={"slot": "collation", "barcode": "3017620422003", "grams": 30}).status_code == 404
    assert len(c.get(f"{url}/day").json()["meals"]) == 1  # un produit introuvable n'enregistre rien
    monkeypatch.setenv("OFF_ENABLED", "0")
    assert c.get(f"{url}/day").json()["barcode"] is False and c.get(f"{url}/barcode/3017620422003").status_code == 503
    c.post("/auth/logout")
    assert c.get(f"{url}/barcode/3017620422003").status_code in (401, 403)


def test_user_correction_replaces_the_estimate_and_feeds_later_ones(ctx):
    c, uid, repo, llm = ctx
    url = f"/users/{uid}/nutrition"
    m = c.post(f"{url}/meals", json={"slot": "déjeuner", "description": "Bourguignon  430 g"}).json()["meal"]
    assert m["analysis"]["kcal"] == 650
    r = c.put(f"{url}/meals/{m['id']}/correction", json={"kcal": 780, "protein_g": 45, "carbs_g": 60, "fat_g": 32})
    a = r.json()["analysis"]
    assert r.status_code == 200 and a["kcal"] == a["kcal_min"] == a["kcal_max"] == 780 and a["corrected"] is True and a["original"]["kcal"] == 650 and a["protein_g"] == 45
    again = c.put(f"{url}/meals/{m['id']}/correction", json={"kcal": 800}).json()["analysis"]  # calories seules : répartition conservée, original d'origine gardé
    assert again["kcal"] == 800 and again["original"]["kcal"] == 650 and again["protein_g"] == 46 and c.get(f"{url}/day").json()["totals"]["kcal"] == 800
    assert c.put(f"{url}/meals/{m['id']}/correction", json={"kcal": 200, "protein_g": 80, "carbs_g": 80, "fat_g": 40}).status_code == 422  # incohérent
    assert c.put(f"{url}/meals/{m['id']}/correction", json={"kcal": 99999}).status_code == 422
    assert c.put(f"{url}/meals/999/correction", json={"kcal": 100}).status_code == 404
    # repas identique (casse et espaces ignorés) + autre repas corrigé : tous deux servent d'exemples, sans identité
    c.post(f"{url}/meals", json={"slot": "dîner", "description": "bourguignon 430 g", "day": str(TODAY)})
    sent = json.loads(llm.calls[-1][0])
    ex = sent["exemples"]
    assert len(ex) == 1 and ex[0]["description"] == "Bourguignon  430 g" and ex[0]["kcal"] == 800 and ex[0]["corrige"] is True
    assert set(ex[0]) == {"description", "kcal", "protein_g", "carbs_g", "fat_g", "corrige"}
    assert "n@example.org" not in json.dumps(sent) and '"R"' not in json.dumps(sent)  # ni e-mail ni nom


def test_other_users_cannot_correct_meals(ctx):
    c, uid, repo, llm = ctx
    mid = c.post(f"/users/{uid}/nutrition/meals", json={"slot": "déjeuner", "description": "x"}).json()["meal"]["id"]
    c.post("/auth/logout")
    other = c.post("/auth/register", json={"name": "E", "email": "e4@example.org", "password": PW}).json()["id"]
    assert c.put(f"/users/{other}/nutrition/meals/{mid}/correction", json={"kcal": 1}).status_code == 404
    assert c.put(f"/users/{uid}/nutrition/meals/{mid}/correction", json={"kcal": 1}).status_code == 403


def test_week_average_is_the_main_figure_and_ignores_unestimated_days(ctx):
    c, uid, repo, llm = ctx
    url = f"/users/{uid}/nutrition"
    for i, k in enumerate((2000, 2400)):
        mid = c.post(f"{url}/meals", json={"slot": "déjeuner", "description": f"repas {i}", "day": str(TODAY - timedelta(days=i)), "estimate": False}).json()["meal"]["id"]
        c.put(f"{url}/meals/{mid}/correction", json={"kcal": k})
    c.post(f"{url}/meals", json={"slot": "dîner", "description": "sans estimation", "day": str(TODAY - timedelta(days=2)), "estimate": False})
    avg = c.get(f"{url}/progress").json()["week_average"]
    assert avg["kcal"] == 2200 and avg["days"] == 2 and avg["target_kcal"] > 1500


def test_estimator_prompts_carry_densities_questions_and_examples_in_both_languages():
    from app.coach import prompts

    for text in (nut_analyze.SYSTEM, prompts.get("meal", nut_analyze.SYSTEM, "en")):
        assert "bourguignon" in text and "poser_des_questions" in text and "reponses" in text and "exemples" in text and '"questions"' in text
    assert "kcal = weight × dish density" in prompts.get("meal", nut_analyze.SYSTEM, "en") and prompts.MARKER in prompts.get("meal", nut_analyze.SYSTEM, "en")
