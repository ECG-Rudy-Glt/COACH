"""Anglais (et toute langue ajoutée) : dictionnaire complet, questionnaire traduit, textes du moteur, prompts du coach, parité serveur / interface."""
import json
import re
import shutil
import subprocess
from datetime import date, timedelta
from pathlib import Path

import pytest
import yaml
from fastapi.testclient import TestClient

from app import i18n
from app.auth import reset_rate_limits
from app.coach import notify, prompts, service
from app.coach.llm import LLMResult
from app.main import app, get_repo
from app.plan.engine import advice, build_profile, outlook, plan_weeks
from app.questionnaire import i18n as q_i18n
from app.questionnaire.bank import load_bank
from app.repo import MemoryRepo
from scripts import i18n_check
from tests.test_plan import EVENT, RUDY, TODAY

ROOT = Path(__file__).resolve().parent.parent
LANGS = [lang for lang in i18n.SUPPORTED if lang != "fr"]
EN = json.loads((ROOT / "app" / "static" / "i18n" / "en.json").read_text(encoding="utf-8"))
HOLE = re.compile(r"\{(\w+)\}")
FRENCH = re.compile(r"[àâçéèêëîïôûùüÿœ]|\b(le|la|les|des|une|un|du|de|pour|avec|votre|vos|est|et|sur|dans|pas|ce|cette|séance|semaine|série|séries|repos|jour|haut|bas|jambes|facile)\b", re.I)
SAME = re.compile(r"^(WOD — )?(AMRAP|EMOM) \d+ min$")  # identiques en français et en anglais
PW = "un-mot-de-passe-solide"


def strings(obj, out=None):
    out = set() if out is None else out
    if isinstance(obj, str):
        out.add(obj)
    elif isinstance(obj, dict):
        [strings(v, out) for v in obj.values()]
    elif isinstance(obj, list | tuple | set):
        [strings(v, out) for v in obj]
    elif hasattr(obj, "__dict__"):
        strings(vars(obj), out)
    return out


@pytest.fixture
def client(monkeypatch):
    reset_rate_limits()
    repo = MemoryRepo()
    app.dependency_overrides[get_repo] = lambda: repo
    c = TestClient(app)
    uid = c.post("/auth/register", json={"name": "Prénom-secret", "email": "secret@example.org", "password": PW}).json()["id"]
    yield c, uid, repo
    app.dependency_overrides.clear()


# ---------- interface ----------
def test_every_ui_text_has_an_english_translation():
    assert i18n_check.missing("en") == []


def test_dictionary_is_well_formed():
    for fr, en in EN.items():
        assert isinstance(en, str) and en.strip(), f"traduction vide : {fr!r}"
        assert set(HOLE.findall(en)) <= set(HOLE.findall(fr)), f"trou inconnu dans la traduction de {fr!r}"
    assert i18n.tr("Accueil", "fr") == "Accueil" and i18n.tr("Accueil", "en") == "Home"
    assert i18n.tr("Texte sans traduction", "en") == "Texte sans traduction"  # retombe sur le français


def test_templates_plurals_numbers_and_sentences():
    assert i18n.tr("Dans 5 jours", "en") == "In 5 days"
    assert i18n.tr("12 exercices", "en") == "12 exercises" and i18n.tr("1 exercice", "en") == "1 exercise"
    assert i18n.tr("Bonjour {userName}", "en", userName="Rudy") == "Hello Rudy"
    assert i18n.tr("Séance A. Visez 8 répétitions à chaque série.", "en").endswith("Aim for 8 reps on every set.")  # texte composé : phrase par phrase
    assert i18n.tr("10 thruster haltères", "en") == "10 dumbbell thrusters"  # {num} ne capture qu'un nombre


# ---------- questionnaire ----------
@pytest.mark.parametrize("lang", LANGS)
def test_questionnaire_translation_is_complete(lang):
    qdir = ROOT / "questions"
    bank = load_bank(qdir)
    assert q_i18n.problems(bank, q_i18n.load_overlay(qdir, lang)) == []
    overlay = q_i18n.load_benchmark_overlay(qdir, lang)
    sections = yaml.safe_load((qdir / "benchmarks.yaml").read_text(encoding="utf-8"))
    assert {s["sport"] for s in sections} <= set(overlay["sections"])
    assert {it["id"] for s in sections for it in s["items"]} <= set(overlay["items"])


def test_bank_endpoint_translates_labels_but_not_identifiers():
    c = TestClient(app)
    fr, en = c.get("/bank?lang=fr").json(), c.get("/bank?lang=en").json()
    assert [q["id"] for q in fr] == [q["id"] for q in en] and [q["options"] for q in fr] == [q["options"] for q in en] and [q["fact_key"] for q in fr] == [q["fact_key"] for q in en]
    assert fr[0]["text"] != en[0]["text"] and "Which sports" in next(q["text"] for q in en if q["id"] == "goal.sports")
    inj = next(q for q in en if q["id"] == "his.injury_timeline")
    assert any(f.get("option_labels", {}).get("genou") == "Knee" for f in inj["fields"] if f["id"] == "zone")
    assert c.get("/bank", headers={"X-Lang": "en"}).json()[0]["text"] == en[0]["text"]  # en-tête de l'interface
    assert c.get("/bank", headers={"Accept-Language": "en-GB,en;q=0.9"}).json()[0]["text"] == en[0]["text"]
    assert c.get("/bank").json()[0]["text"] == fr[0]["text"]  # le français reste la langue par défaut


def test_benchmarks_page_is_translated(client):
    c, uid, _ = client
    c.post(f"/users/{uid}/answers", json={"question_id": "goal.sports", "value": ["strength"]})
    titles = [s["title"] for s in c.get(f"/users/{uid}/benchmarks", headers={"X-Lang": "en"}).json()["sections"]]
    assert titles == ["Strength training"]


# ---------- textes du moteur ----------
def test_engine_texts_are_translated():
    profiles = [
        (RUDY, [EVENT]),
        ({**RUDY, "history.injuries": ["genou"], "goal.physique_focus": ["épaules", "bras"]}, []),
        ({**RUDY, "sports.practiced": ["running", "strength", "crossfit", "hyrox"], "strength.sessions_per_week": 2}, [EVENT]),
        ({**RUDY, "sports.practiced": ["running"], "running.weekly_km_8w": 5, "history.recent_break": "oui blessure"}, [{**EVENT, "details": {"distance_km": 21}}]),
        ({**RUDY, "sports.practiced": ["strength"], "constraints.training_days": 3, "strength.sessions_per_week": 3,
          "strength.equipment": ["haltères", "élastiques", "poids de corps"]}, []),
        ({**RUDY, "sports.practiced": ["running", "cycling", "strength"]}, [{"status": "active", "kind": "performance", "target_date": date(2028, 9, 30), "priority": "principal",
                                                                             "title": "10 km sub 40", "details": {"distance_km": 10, "target_time": "39:59"}}]),
    ]
    found: set[str] = set()
    for facts, goals in profiles:
        p = build_profile(facts, goals, TODAY)
        strings([plan_weeks(p, TODAY, weeks=8), outlook(p, TODAY), advice(p)], found)
    untranslated = sorted(s for s in found if FRENCH.search(s) and i18n.tr(s, "en") == s and not SAME.match(s))
    assert untranslated == []
    assert any(i18n.tr(s, "en") != s for s in found)


def test_notification_texts_are_translated():
    for title, body in notify.FALLBACK.values():
        assert i18n.tr(title, "en") != title and i18n.tr(body, "en") != body
    repo = MemoryRepo()
    uid = repo.create_account("A", "a@example.org", "x")
    repo.add_sessions(uid, [{"day": date.today() + timedelta(days=1), "kind": "run_easy", "title": "Footing facile", "duration_min": 40, "details": {}, "rules": ["C1"], "notes": []}])
    with i18n.use("en"):
        subject, text = notify.fallback_digest(repo, uid, date.today())
    assert subject == "Your week at a glance" and "Easy jog" in text and "Nutrition:" in text and not FRENCH.search(text.replace("Semaine", ""))
    assert notify.fallback_digest(repo, uid, date.today())[0] == "Votre semaine en un coup d'œil"


# ---------- langue du compte ----------
def test_language_is_stored_on_the_account(client):
    c, uid, repo = client
    assert c.get("/auth/me").json()["lang"] is None
    assert c.put("/auth/language", json={"lang": "en-GB"}).json() == {"lang": "en"}
    assert c.get("/auth/me").json()["lang"] == "en" and repo.get_language(uid) == "en"
    assert c.put("/auth/language", json={"lang": "de"}).status_code == 422
    c.post("/auth/logout")
    assert c.post("/auth/login", json={"email": "secret@example.org", "password": PW}).json()["lang"] == "en"


def test_language_resolution():
    assert i18n.resolve("en", "fr", "fr") == "en" and i18n.resolve(None, "EN", None) == "en"
    assert i18n.resolve(None, None, "de-DE,en;q=0.8") == "en" and i18n.resolve(None, None, "de") == "fr"


# ---------- coach IA ----------
class FakeLLM:
    def __init__(self):
        self.system = ""

    def complete(self, system, user, max_tokens, model=None, history=None, image=None, json_mode=False):
        self.system = system
        return LLMResult(json.dumps({"summary": "ok", "adherence": "", "questions": [], "proposals": [], "reply": "ok"}), 10, 10, "m")


def test_prompts_exist_in_every_language_with_an_explicit_answer_language():
    for lang in LANGS:
        data = prompts._load(lang)
        for name in ("review", "sources_rule", "chat", "intake", "checkin", "digest", "digest_nutrition", "json_retry", "meal"):
            assert data.get(name), f"prompt {name} absent pour {lang}"
        for name in ("review", "chat", "intake", "checkin", "digest", "meal"):
            assert prompts.MARKER in data[name] and i18n.LANG_NAMES[lang] in data[name]
    # les clés JSON et les noms d'actions ne sont jamais traduits
    for needle in ('"proposals"', "reduce|swap_easy|move", '"session_id"'):
        assert needle in prompts._load("en")["review"] and needle in service.SYSTEM
    assert prompts.get("review", service.SYSTEM, "fr") == service.SYSTEM
    assert prompts.with_language("x", "fr") == "x" and prompts.with_language("x", "en").endswith("in English. JSON keys, identifiers, rule ids and action names stay unchanged.")


@pytest.mark.parametrize(("lang", "marker"), [("fr", "VOUVOIES"), ("en", "You are the coach")])
def test_review_uses_the_prompt_of_the_request_language(client, monkeypatch, lang, marker):
    c, uid, repo = client
    monkeypatch.setenv("ANTHROPIC_API_KEY", "test")
    llm, old = FakeLLM(), app.state.llm
    app.state.llm = llm
    try:
        assert c.post(f"/users/{uid}/coach/review", headers={"X-Lang": lang}).status_code == 200
    finally:
        app.state.llm = old
    assert marker in llm.system
    if lang == "en":
        assert "English" in llm.system and "VOUVOIES" not in llm.system


def test_chat_and_digest_follow_the_language(client, monkeypatch):
    c, uid, repo = client
    monkeypatch.setenv("ANTHROPIC_API_KEY", "test")
    llm, old = FakeLLM(), app.state.llm
    app.state.llm = llm
    try:
        c.post(f"/users/{uid}/coach/chat", json={"message": "Hello coach"}, headers={"X-Lang": "en"})
        assert "chatting with them" in llm.system and "CONTEXT:" in llm.system and "CONTEXTE" not in llm.system
        c.post(f"/users/{uid}/coach/chat", json={"message": "Bonjour"}, headers={"X-Lang": "fr"})
        assert "tu discutes avec lui" in llm.system and "CONTEXTE :" in llm.system
    finally:
        app.state.llm = old


def test_untranslated_prompt_falls_back_to_french_plus_language_rule():
    with i18n.use("en"):
        assert prompts.get("inconnu", "Texte français") == "Texte français" + prompts.language_rule("en")


# ---------- parité avec i18n.js ----------
@pytest.mark.skipif(shutil.which("node") is None, reason="node absent")
def test_client_and_server_translate_identically(tmp_path):
    samples = [k for k in EN if "{" not in k][:200] + ["Dans 5 jours", "12 exercices", "1 exercice", "3 jours d'entraînement", "10 thruster haltères",
                                                       "Séance A. Visez 8 répétitions à chaque série.", "AMRAP 14 min — tours de : 12 cal rameur, 10 thruster haltères, 6 tractions",
                                                       "Gardez 40 kg et visez 8 répétitions à chaque série.", "Texte inconnu, tout à fait."]
    script = tmp_path / "t.js"
    script.write_text("const I = require(process.argv[2]); const d = JSON.parse(require('fs').readFileSync(process.argv[3], 'utf8')); I.setLocale('en', d);"
                      "console.log(JSON.stringify(JSON.parse(require('fs').readFileSync(0, 'utf8')).map((s) => I.t(s))));", encoding="utf-8")
    out = subprocess.run(["node", str(script), str(ROOT / "app" / "static" / "i18n.js"), str(ROOT / "app" / "static" / "i18n" / "en.json")],
                         input=json.dumps(samples), capture_output=True, text=True, check=True).stdout
    assert json.loads(out) == [i18n.tr(s, "en") for s in samples]

