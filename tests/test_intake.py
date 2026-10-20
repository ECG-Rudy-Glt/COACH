"""Accueil : questions essentielles, puis analyse du coach (questions manquantes choisies par l'IA, validées par le serveur)."""
import json
from datetime import date

import pytest
from fastapi.testclient import TestClient
from test_coach import PW, FakeLLM

from app.coach import intake
from app.coach.llm import NoLLM
from app.main import app, get_repo
from app.questionnaire.engine import next_questions, pending, progress
from app.questionnaire.models import Fact
from app.repo import MemoryRepo

ANSWERS = {  # une personne qui court et fait de la musculation
    "sports.practiced": ["running", "strength"], "goal.primary": ["performance"], "body.birth_year": 1995, "body.sex": "homme", "body.height": 180,
    "body.weight": 75, "health.disclaimer": "oui", "health.red_flags": ["aucun"], "constraints.training_days": 4, "constraints.weekday_session_max_min": 60,
    "history.injuries": ["aucune"], "running.weekly_km_8w": 20, "strength.level": "intermédiaire",
}


@pytest.fixture
def ctx(monkeypatch):
    from app.auth import reset_rate_limits

    reset_rate_limits()
    monkeypatch.setenv("ANTHROPIC_API_KEY", "test")
    repo, llm = MemoryRepo(), FakeLLM()
    app.dependency_overrides[get_repo] = lambda: repo
    old = app.state.llm
    app.state.llm = llm
    c = TestClient(app)
    uid = c.post("/auth/register", json={"name": "Prénom-secret", "email": "secret@example.org", "password": PW}).json()["id"]
    yield c, uid, repo, llm
    app.state.llm = old
    app.dependency_overrides.clear()


def answer_essentials(repo, uid, keys=None):
    repo.add_facts(uid, [Fact(key=k, value=v, source="questionnaire") for k, v in ANSWERS.items() if keys is None or k in keys])


def test_essentials_are_a_short_adaptive_path():
    bank = app.state.bank
    ess = [q for q in bank if q.essential]
    assert 10 <= len(ess) <= 14 and len({q.fact_key for q in ess}) == len(ess)
    assert {"goal.sports", "he.disclaimer", "he.red_flags", "his.injuries"} <= {q.id for q in ess}  # sécurité et blessures d'abord
    facts = []
    asked = 0
    while True:
        q = next_questions(bank, facts, 1, essential=True)
        if not q:
            break
        asked += 1
        value = ANSWERS.get(q[0].fact_key, "x")
        facts.append(Fact(key=q[0].fact_key, value=value, source="questionnaire"))
        assert asked < 20
    assert asked == 13  # course + musculation : toutes les essentielles s'appliquent
    assert progress(bank, facts)["essential"] == {"answered": 13, "remaining": 0}
    assert progress(bank, [])["essential"]["remaining"] < 13  # sans sport choisi, celles qui en dépendent ne sont pas encore visibles
    only_strength = [Fact(key="sports.practiced", value=["strength"], source="questionnaire")]
    assert not any(q.id == "run.recent_volume" for q in next_questions(bank, only_strength, 40, essential=True))
    assert len(pending(bank, facts)) > 20  # le reste de la banque attend, au fil de l'eau


def test_questions_next_can_be_limited_to_essentials(ctx):
    c, uid, repo, llm = ctx
    r = c.get(f"/users/{uid}/questions/next?tier=essential&n=10").json()
    assert r["questions"]
    ids = {q["id"] for q in r["questions"]}
    assert ids <= {q.id for q in app.state.bank if q.essential} and "essential" in r and r["essential"]["remaining"] >= 1
    assert c.get(f"/users/{uid}/profile").json()["intake_done"] is False


def test_llm_picks_questions_and_the_server_validates_them(ctx):
    c, uid, repo, llm = ctx
    answer_essentials(repo, uid)
    pend = [q.id for q in pending(app.state.bank, repo.list_facts(uid))]
    assert "con.work" in pend
    llm.out = {"enough": False, "message": "Il me manque deux informations.",
               "ask": [{"id": "con.work", "reason": "Un travail physique change la récupération."}, {"id": "con.work", "reason": "doublon"},
                       {"id": "inventee.question", "reason": "n'existe pas"}, {"id": "ANSWERED", "reason": "x"}] + [{"id": i, "reason": "r"} for i in pend[:10]],
               "clarifications": [{"question": "Q1 " + "x" * 400, "reason": "a"}, {"question": "Q2", "reason": "b"}, {"question": "Q3", "reason": "c"}]}
    r = c.post(f"/users/{uid}/coach/intake").json()
    assert r["status"] == "questions" and r["source"] == "llm" and r["message"] == "Il me manque deux informations."
    got = [q["id"] for q in r["questions"]]
    assert got[0] == "con.work" and len(got) == len(set(got)) == 6 and "inventee.question" not in got  # identifiants connus, sans doublon, 6 au plus
    assert r["questions"][0]["reason"].startswith("Un travail physique") and "show_if" not in r["questions"][0] and "fact_key" not in r["questions"][0]
    assert [x["question"][:2] for x in r["clarifications"]] == ["Q1", "Q2"] and len(r["clarifications"][0]["question"]) == 160  # 2 précisions, texte borné
    sent = llm.prompts[0]
    assert "Prénom-secret" not in sent and "secret@example.org" not in sent  # aucune identité envoyée
    payload = json.loads(sent)
    assert "con.work" in {q["id"] for q in payload["questions_possibles"]} and payload["profil"]["sports.practiced"] == ["running", "strength"]
    assert "goal.sports" not in {q["id"] for q in payload["questions_possibles"]}  # ce qui est déjà répondu n'est pas redemandé


def test_result_is_cached_and_answered_questions_disappear(ctx):
    c, uid, repo, llm = ctx
    answer_essentials(repo, uid)
    llm.out = {"enough": False, "message": "m", "ask": [{"id": "con.work", "reason": "r"}, {"id": "con.sleep", "reason": "r"}],
               "clarifications": [{"question": "Votre blessure ancienne ?", "reason": "r"}]}
    first = c.post(f"/users/{uid}/coach/intake").json()
    again = c.post(f"/users/{uid}/coach/intake").json()
    assert len(llm.prompts) == 1 and again == first  # rouvrir l'application ne relance pas l'IA
    assert c.get(f"/users/{uid}/profile").json()["intake_done"] is True
    c.post(f"/users/{uid}/answers", json={"question_id": "con.work", "value": "sédentaire"})
    assert [q["id"] for q in c.post(f"/users/{uid}/coach/intake").json()["questions"]] == ["con.sleep"]
    r = c.post(f"/users/{uid}/coach/intake/clarification", json={"index": 0, "answer": "Entorse il y a 2 ans, plus de gêne."})
    assert r.status_code == 201 and r.json()["clarifications"] == []
    fact = [f for f in repo.list_facts(uid) if f.key == "coach.clarification.0"][0]
    assert fact.value == {"question": "Votre blessure ancienne ?", "answer": "Entorse il y a 2 ans, plus de gêne."} and fact.source == "llm_question"
    assert c.post(f"/users/{uid}/coach/intake/clarification", json={"index": 3, "answer": "x"}).status_code == 404
    c.post(f"/users/{uid}/answers", json={"question_id": "con.sleep", "value": 7})
    assert c.post(f"/users/{uid}/coach/intake").json()["status"] == "ready"
    from app.coach import service
    assert service.build_context(repo, uid, date.today())["precisions_declarees"][0]["answer"].startswith("Entorse")  # le coach les relit


def test_enough_means_ready_and_the_page_can_open(ctx):
    c, uid, repo, llm = ctx
    answer_essentials(repo, uid)
    llm.out = {"enough": True, "message": "Tout est clair.", "ask": [], "clarifications": []}
    r = c.post(f"/users/{uid}/coach/intake").json()
    assert r["status"] == "ready" and r["message"] == "Tout est clair." and r["questions"] == []


def test_without_ai_the_required_questions_remain_the_rule(ctx):
    c, uid, repo, llm = ctx
    app.state.llm = NoLLM()
    answer_essentials(repo, uid)
    r = c.post(f"/users/{uid}/coach/intake").json()
    required = [q.id for q in pending(app.state.bank, repo.list_facts(uid)) if q.required][:6]
    assert r["source"] == "rules" and r["status"] == "questions" and [q["id"] for q in r["questions"]] == required
    assert all(q["reason"] for q in r["questions"]) and llm.prompts == []


@pytest.mark.parametrize("failure", ["error", "garbage"])
def test_ai_failure_falls_back_to_the_rule_and_is_logged(ctx, failure):
    c, uid, repo, llm = ctx
    answer_essentials(repo, uid)
    if failure == "error":
        llm.fail = True
    else:
        llm.out = "pas du json du tout"
    r = c.post(f"/users/{uid}/coach/intake").json()
    assert r["source"] == "rules" and r["questions"]
    assert repo.llm_calls_since(uid, "intake", __import__("datetime").datetime(2000, 1, 1, tzinfo=__import__("datetime").UTC)) == 1  # l'appel est compté


def test_budget_exhausted_skips_the_ai(ctx, monkeypatch):
    c, uid, repo, llm = ctx
    answer_essentials(repo, uid)
    monkeypatch.setenv("LLM_MONTHLY_BUDGET_EUR", "0")
    r = c.post(f"/users/{uid}/coach/intake").json()
    assert r["source"] == "rules" and llm.prompts == []


def test_measured_facts_are_labelled_so_the_ai_does_not_ask_again(ctx):
    c, uid, repo, llm = ctx
    answer_essentials(repo, uid)
    repo.add_facts(uid, [Fact(key="running.weekly_km_12m", value=31.5, source="garmin")])
    llm.out = {"enough": True, "message": "ok", "ask": [], "clarifications": []}
    c.post(f"/users/{uid}/coach/intake")
    payload = json.loads(llm.prompts[0])
    assert payload["mesures_montre"] == {"running.weekly_km_12m": 31.5} and "running.weekly_km_12m" not in payload["profil"]


def test_force_is_bounded_per_day(ctx):
    c, uid, repo, llm = ctx
    answer_essentials(repo, uid)
    llm.out = {"enough": True, "message": "ok", "ask": [], "clarifications": []}
    codes = [c.post(f"/users/{uid}/coach/intake", json={"force": True}).status_code for _ in range(5)]
    assert codes == [200, 200, 200, 429, 429]


def test_validate_unit():
    cands = [q for q in app.state.bank if q.id in ("con.work", "con.sleep")]
    out = intake.validate({"ask": [{"id": "con.sleep", "reason": "x" * 500}, "pas un dict", {"id": "con.work"}], "clarifications": "n'importe quoi", "message": None}, cands)
    assert [a["id"] for a in out["ask"]] == ["con.sleep", "con.work"] and len(out["ask"][0]["reason"]) == 160 and out["clarifications"] == [] and out["message"] == ""
