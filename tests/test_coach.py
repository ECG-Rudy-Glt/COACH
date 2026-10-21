import json
from datetime import date, timedelta

import pytest
import yaml
from fastapi.testclient import TestClient

from app.coach import service
from app.coach.llm import LLMError, LLMResult
from app.main import app, get_repo
from app.repo import MemoryRepo

PW = "un-mot-de-passe-solide"
TODAY = date.today()


class FakeLLM:
    def __init__(self):
        self.out: dict | str = {}
        self.prompts: list[str] = []
        self.fail = False

    def complete(self, system, user, max_tokens, model=None, history=None, image=None, json_mode=False):
        self.prompts.append(user)
        self.history = history
        self.system = system
        if self.fail:
            raise LLMError("Le service IA est injoignable.")
        text = self.out if isinstance(self.out, str) else json.dumps(self.out)
        return LLMResult(text, 4000, 500, model or "claude-sonnet-5-5")


def session(day, kind="run_easy", minutes=60):
    return {"day": day, "kind": kind, "title": "S", "duration_min": minutes, "details": {"zone": "z2"}, "rules": ["C1"], "notes": []}


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
    repo.add_sessions(uid, [session(TODAY + timedelta(days=2), "run_quality", 60), session(TODAY + timedelta(days=4), "run_long", 90),
                            session(TODAY + timedelta(days=1), "strength_lower", 45)])
    yield c, uid, repo, llm
    app.state.llm = old
    app.dependency_overrides.clear()


def ids(repo, uid):
    return {s["kind"]: s["id"] for s in repo.list_sessions(uid, TODAY, TODAY + timedelta(days=15))}


def test_rules_digest_matches_rules_document():
    import re

    doc = (service.ROOT / "docs" / "rules.md").read_text(encoding="utf-8")
    assert set(re.findall(r"^\| ((?:ST|[SGCMIRN])\d+) \|", doc, re.M)) == set(yaml.safe_load((service.ROOT / "data" / "rules_digest.yaml").read_text()))


def test_review_stores_memory_and_prompt_has_no_identity(ctx):
    c, uid, repo, llm = ctx
    sid = ids(repo, uid)["run_long"]
    llm.out = {"summary": "Bonne semaine.", "adherence": "2 séances sur 3.", "questions": ["Comment va le genou ?"],
               "proposals": [{"session_id": sid, "action": "reduce", "factor": 0.8, "reason": "Fatigue", "rule_ids": ["G1", "G2"]}]}
    r = c.post(f"/users/{uid}/coach/review")
    assert r.status_code == 200 and r.json()["summary"] == "Bonne semaine."
    p = r.json()["data"]["proposals"][0]
    assert p["action"] == "reduce" and p["new_duration_min"] == 72 and p["status"] == "proposed"
    prompt = llm.prompts[0]
    assert "Prénom-secret" not in prompt and "secret@example.org" not in prompt  # aucune identité envoyée
    assert "G2" in prompt and "seances_a_venir" in prompt
    # le bilan précédent est transmis au suivant (le coach connaît son historique)
    llm.out = {"summary": "Suite.", "proposals": []}
    c.post(f"/users/{uid}/coach/review")
    assert "Bonne semaine." in llm.prompts[1]


def test_invalid_proposals_are_rejected_by_the_server(ctx):
    c, uid, repo, llm = ctx
    k = ids(repo, uid)
    llm.out = {"summary": "x", "proposals": [
        {"session_id": k["run_long"], "action": "reduce", "factor": 1.2, "reason": "plus", "rule_ids": ["G1"]},  # augmente la charge
        {"session_id": k["run_long"], "action": "reduce", "factor": 0.8, "reason": "ok", "rule_ids": ["X99"]},  # règle inventée
        {"session_id": 99999, "action": "reduce", "factor": 0.8, "reason": "ok", "rule_ids": ["G1"]},  # séance inexistante
        {"session_id": k["run_long"], "action": "swap_easy", "reason": "ok", "rule_ids": ["C1"]},  # seulement la qualité
        {"session_id": k["strength_lower"], "action": "move", "to_day": (TODAY + timedelta(days=3)).isoformat(),
         "reason": "ok", "rule_ids": ["I2"]},  # jambes la veille de la sortie longue
        {"session_id": k["run_quality"], "action": "delete", "reason": "ok", "rule_ids": ["G1"]},  # action inconnue
    ]}
    d = c.post(f"/users/{uid}/coach/review").json()["data"]
    assert d["proposals"] == [] and len(d["rejected"]) == 6


def test_apply_and_dismiss_modify_only_that_session(ctx):
    c, uid, repo, llm = ctx
    k = ids(repo, uid)
    llm.out = {"summary": "x", "proposals": [
        {"session_id": k["run_quality"], "action": "swap_easy", "reason": "Fatigue", "rule_ids": ["C1", "R1"]},
        {"session_id": k["run_long"], "action": "reduce", "factor": 0.6, "reason": "Charge élevée", "rule_ids": ["G1"]}]}
    mem = c.post(f"/users/{uid}/coach/review").json()
    mid = mem["id"]
    assert c.post(f"/users/{uid}/coach/proposals/{mid}/0/apply").json()["status"] == "applied"
    after = {s["id"]: s for s in repo.list_sessions(uid, TODAY, TODAY + timedelta(days=15))}
    assert after[k["run_quality"]]["kind"] == "run_easy" and "Ajusté par le coach" in after[k["run_quality"]]["notes"][-1]
    assert after[k["run_long"]]["duration_min"] == 90  # l'autre proposition n'est pas appliquée
    assert c.post(f"/users/{uid}/coach/proposals/{mid}/0/apply").status_code == 409  # déjà traitée
    assert c.post(f"/users/{uid}/coach/proposals/{mid}/1/dismiss").json()["status"] == "dismissed"
    assert repo.list_sessions(uid, TODAY, TODAY + timedelta(days=15))[2]["duration_min"] == 90
    assert c.post(f"/users/{uid}/coach/proposals/{mid}/9/apply").status_code == 404


def test_budget_cap_blocks_calls_and_failures_are_logged(ctx, monkeypatch):
    c, uid, repo, llm = ctx
    llm.out = {"summary": "x", "proposals": []}
    monkeypatch.setenv("LLM_MONTHLY_BUDGET_EUR", "0.015")
    monkeypatch.setenv("LLM_PRICE_IN_EUR_PER_MTOK", "3")  # tarifs forcés : le plafond se teste sans dépendre de la table des modèles
    monkeypatch.setenv("LLM_PRICE_OUT_EUR_PER_MTOK", "15")
    assert c.post(f"/users/{uid}/coach/review").status_code == 200  # coût estimé 4000×3€/M + 500×15€/M ≈ 0,0195 €
    assert c.get(f"/users/{uid}/coach").json()["budget"]["spent_eur"] >= 0.019
    r = c.post(f"/users/{uid}/coach/review")
    assert r.status_code == 429 and "plafond" in r.json()["detail"]


def test_llm_errors_and_garbage_are_handled(ctx):
    c, uid, repo, llm = ctx
    llm.fail = True
    assert c.post(f"/users/{uid}/coach/review").status_code == 502
    llm.fail = False
    llm.out = "Voici mon avis sans JSON"
    assert c.post(f"/users/{uid}/coach/review").status_code == 502
    llm.out = "```json\n" + json.dumps({"summary": "ok", "proposals": []}) + "\n```"
    assert c.post(f"/users/{uid}/coach/review").json()["summary"] == "ok"


def test_red_flag_blocks_review_and_daily_limit(ctx):
    c, uid, repo, llm = ctx
    llm.out = {"summary": "x", "proposals": []}
    for _ in range(service.MAX_REVIEWS_PER_DAY):
        assert c.post(f"/users/{uid}/coach/review").status_code == 200
    assert c.post(f"/users/{uid}/coach/review").status_code == 429
    c.post(f"/users/{uid}/answers", json={"question_id": "he.red_flags", "value": ["palpitations"]})
    repo._llm.clear()
    assert c.post(f"/users/{uid}/coach/review").status_code == 409  # S1


def test_session_adaptations_reach_the_coach_and_are_sanitised(ctx):
    c, uid, repo, llm = ctx
    sid = ids(repo, uid)["run_long"]
    r = c.patch(f"/users/{uid}/plan/sessions/{sid}", json={"status": "planned", "logged": {
        "adaptation": "J'ai remplacé le squat par une presse à cuisses, genou sensible.", "changes": ["douleur", "n'importe quoi"], "evil": 1}})
    assert r.status_code == 200 and r.json()["logged"] == {"adaptation": "J'ai remplacé le squat par une presse à cuisses, genou sensible.",
                                                         "changes": ["douleur"]}
    llm.out = {"summary": "x", "proposals": []}
    c.post(f"/users/{uid}/coach/review")
    assert "presse à cuisses" in llm.prompts[0] and "adaptation_declaree" in llm.prompts[0]
    big = c.patch(f"/users/{uid}/plan/sessions/{sid}", json={"status": "planned", "logged": {"note": "x" * 30000}})
    assert big.status_code == 422


def test_chat_stores_thread_and_reads_questions(ctx):
    c, uid, repo, llm = ctx
    llm.out = {"summary": "Bonne semaine.", "adherence": "ok", "questions": ["Comment sont vos jambes ?", "Quel sommeil cette semaine ?"], "proposals": []}
    assert c.post(f"/users/{uid}/coach/review").status_code == 200
    msgs = c.get(f"/users/{uid}/coach/chat").json()["messages"]
    assert msgs[0]["role"] == "assistant" and "1. Comment sont vos jambes" in msgs[0]["body"]  # les questions arrivent dans la discussion
    llm.out = {"reply": "Merci, je note le sommeil court.", "motivation": "baisse", "remember": "Dort 5 h par nuit en semaine"}
    r = c.post(f"/users/{uid}/coach/chat", json={"message": "Jambes lourdes et je dors 5 h, j'ai plus trop envie"}).json()["messages"]
    assert [m["role"] for m in r] == ["user", "assistant"] and r[1]["meta"]["motivation"] == "baisse"
    assert llm.history == []  # la question du coach (assistant) ne peut pas ouvrir l'historique : il commence par l'utilisateur
    assert "Dort 5 h par nuit en semaine" in [m["body"] for m in repo.list_memory(uid, "decision", 5)]
    llm.out = {"reply": "Bien noté.", "motivation": "ok", "remember": ""}
    c.post(f"/users/{uid}/coach/chat", json={"message": "Merci"})
    assert [h["role"] for h in llm.history] == ["user", "assistant"]
    assert "Dort 5 h par nuit" in llm.system  # la note gardée est dans le contexte suivant


def test_chat_plain_text_reply_empty_and_failure(ctx):
    c, uid, repo, llm = ctx
    llm.out = "Réponse sans JSON."
    assert c.post(f"/users/{uid}/coach/chat", json={"message": "Salut"}).json()["messages"][1]["body"] == "Réponse sans JSON."
    assert c.post(f"/users/{uid}/coach/chat", json={"message": "   "}).status_code == 422
    llm.fail = True
    assert c.post(f"/users/{uid}/coach/chat", json={"message": "Encore"}).status_code == 502
    bodies = [m["body"] for m in c.get(f"/users/{uid}/coach/chat").json()["messages"]]
    assert "Encore" in bodies  # le message de l'utilisateur n'est pas perdu


class FakeNotifier:
    def __init__(self):
        self.sent: list[tuple] = []
        self.fail = False

    def available(self):
        return {"push": True, "email": True}

    def push(self, topic, title, body, priority=3):
        from app.coach.notify import NotifyError
        if self.fail:
            raise NotifyError("Le serveur de notifications est injoignable ou a refusé l'envoi.")
        self.sent.append(("push", topic, title, body))

    def email(self, to, subject, text):
        self.sent.append(("email", to, subject, text))


def _prefs(repo, uid, **kw):
    repo.set_prefs(uid, {"ntfy_topic": "coach-secret-topic", "email": "moi@example.org", "push_enabled": True, "email_enabled": False, **kw})


def test_notification_prefs_validation_and_test_send(ctx):
    c, uid, repo, llm = ctx
    n = FakeNotifier()
    app.state.notifier = n
    assert c.put(f"/users/{uid}/coach/notifications", json={"ntfy_topic": "x", "push_enabled": True}).status_code == 422
    assert c.put(f"/users/{uid}/coach/notifications", json={"push_enabled": True}).status_code == 422  # canal sans destinataire
    ok = c.put(f"/users/{uid}/coach/notifications", json={"ntfy_topic": "coach-secret-topic", "push_enabled": True}).json()
    assert ok["push_enabled"] and ok["server"]["push"]
    assert c.post(f"/users/{uid}/coach/notifications/test/push").json() == {"sent": True} and n.sent[0][1] == "coach-secret-topic"


def test_checkin_fires_on_signal_with_fallback_and_respects_gap(ctx):
    from app.coach import notify
    c, uid, repo, llm = ctx
    n = FakeNotifier()
    _prefs(repo, uid)
    assert notify.checkin(repo, llm, n, uid, TODAY) is None  # aucun signal : silence
    repo.add_sessions(uid, [session(TODAY - timedelta(days=2)), session(TODAY - timedelta(days=4))])
    llm.fail = True  # le LLM tombe : le message de repli part quand même
    assert notify.checkin(repo, llm, n, uid, TODAY) == "séances_manquées"
    assert n.sent[0][0] == "push" and "reprend" in n.sent[0][2]
    assert notify.checkin(repo, llm, n, uid, TODAY) is None  # pas de seconde alerte avant 3 jours
    assert len(n.sent) == 1


def test_checkin_uses_llm_text_and_chat_motivation_signal(ctx):
    from app.coach import notify
    c, uid, repo, llm = ctx
    n = FakeNotifier()
    _prefs(repo, uid)
    repo.add_message(uid, "assistant", "Courage", {"motivation": "baisse"})
    llm.out = {"title": "Une séance courte ?", "body": "Dix minutes de marche rapide comptent aussi."}
    assert notify.checkin(repo, llm, n, uid, TODAY) == "motivation_en_baisse"
    assert n.sent[0][2:] == ("Une séance courte ?", "Dix minutes de marche rapide comptent aussi.")


def test_failed_push_is_logged_and_digest_is_weekly_email(ctx):
    from app.coach import notify
    c, uid, repo, llm = ctx
    n = FakeNotifier()
    _prefs(repo, uid, push_enabled=False, email_enabled=True)
    from app.questionnaire.models import Fact
    repo.add_facts(uid, [Fact(key="sports.practiced", value=["running", "strength"], source="user")])
    llm.out = {"subject": "Vos conseils", "intro": "Bonne semaine.", "sections": [{"discipline": "Course", "tips": ["Footing facile", "Hydratation"]}], "closing": "À dimanche."}
    assert notify.weekly_digest(repo, llm, n, uid, TODAY)
    kind, to, subject, text = n.sent[0]
    assert kind == "email" and to == "moi@example.org" and "COURSE" in text and "- Footing facile" in text
    assert not notify.weekly_digest(repo, llm, n, uid, TODAY)  # un seul mail par semaine
    _prefs(repo, uid, push_enabled=True, email_enabled=False)
    n.fail = True
    repo.add_sessions(uid, [session(TODAY - timedelta(days=2)), session(TODAY - timedelta(days=4))])
    notify.checkin(repo, llm, n, uid, TODAY)
    assert repo.last_notify(uid, "checkin", ok_only=True) is None and repo.last_notify(uid, "checkin", ok_only=False)


def test_notification_topic_error_is_readable(ctx):
    c, uid, repo, llm = ctx
    r = c.put(f"/users/{uid}/coach/notifications", json={"ntfy_topic": "mon sujet avec espaces", "push_enabled": True})
    assert r.status_code == 422 and isinstance(r.json()["detail"], str) and "8 à 64" in r.json()["detail"]
    long = c.put(f"/users/{uid}/coach/notifications", json={"ntfy_topic": "a" * 100, "push_enabled": True})
    assert long.status_code == 422 and isinstance(long.json()["detail"], str)  # message clair, pas une erreur de schéma


def test_web_push_subscribe_send_and_cleanup(ctx):
    from app.coach import notify
    c, uid, repo, llm = ctx

    class Phone(FakeNotifier):
        gone = False

        def available(self):
            return {"push": False, "webpush": True, "email": False}

        def webpush(self, sub, title, body):
            if self.gone:
                raise notify.Gone("Appareil désabonné.")
            self.sent.append(("webpush", sub["endpoint"], title, body))

    n = Phone()
    app.state.notifier = n
    sub = {"endpoint": "https://web.push.apple.com/abcdefghijklmnop", "keys": {"p256dh": "BPubKeyPubKeyPubKey", "auth": "authsecret"}}
    assert c.post(f"/users/{uid}/coach/push/subscribe", json={"endpoint": "http://pas-https.example/abcdefghij", "keys": sub["keys"]}).status_code == 422
    assert c.post(f"/users/{uid}/coach/push/subscribe", json=sub).json() == {"devices": 1}
    assert repo.get_prefs(uid)["push_enabled"]  # s'abonner active le canal
    assert c.post(f"/users/{uid}/coach/notifications/test/push").json() == {"sent": True} and n.sent[0][0] == "webpush"
    # une alerte part sur l'appareil, sans sujet ntfy
    repo.add_sessions(uid, [session(TODAY - timedelta(days=2)), session(TODAY - timedelta(days=4))])
    llm.fail = True
    assert notify.checkin(repo, llm, n, uid, TODAY) == "séances_manquées" and n.sent[-1][0] == "webpush"
    # appareil désinstallé : l'abonnement est supprimé au prochain envoi
    n.gone = True
    try:
        notify.send_push(repo, n, uid, "t", "b", repo.get_prefs(uid))
    except notify.NotifyError:
        pass
    assert repo.list_subscriptions(uid) == []


def test_single_missed_session_and_missing_meals_trigger_signals(ctx):
    from app.coach.notify import signals

    c, uid, repo, llm = ctx
    y = TODAY - timedelta(days=1)
    repo.add_sessions(uid, [session(y, "run_easy", 40)])
    repo.add_sessions(uid, [{**session(y - timedelta(days=2), "strength_upper", 60), "status": "planned"}])
    sig = signals(repo, uid, TODAY)
    assert "séance_manquée_hier" in sig or "séances_manquées" in sig
    for i in (1, 2, 3):
        repo.add_meal(uid, TODAY - timedelta(days=i), "déjeuner", "x", None)
    assert "repas_non_saisis" in signals(repo, uid, TODAY)
    repo.add_meal(uid, TODAY, "déjeuner", "x", None)
    assert "repas_non_saisis" not in signals(repo, uid, TODAY)


class StubNotifier:
    def __init__(self):
        self.mails = []

    def email(self, to, subject, text):
        self.mails.append((to, subject, text))


def _digest_setup(repo, uid):
    repo.set_prefs(uid, {"email_enabled": True, "email": "a@example.org", "push_enabled": False, "ntfy_topic": ""})
    repo.add_facts(uid, [__import__("app.questionnaire.models", fromlist=["Fact"]).Fact(key="sports.practiced", value=["running", "strength"])])


def test_digest_retries_invalid_json_then_falls_back_to_a_plain_mail(ctx):
    from app.coach import notify

    c, uid, repo, llm = ctx
    _digest_setup(repo, uid)
    repo.add_sessions(uid, [session(TODAY + timedelta(days=2), "run_easy", 40)])
    repo.add_meal(uid, TODAY, "déjeuner", "x", None)
    stub = StubNotifier()
    llm.out = '{"subject": "x", "sections": [oups'  # JSON invalide aux deux essais
    assert notify.weekly_digest(repo, llm, stub, uid, TODAY) is True
    assert len(llm.prompts) == 2 and "JSON valide" in llm.prompts[0] or len(llm.prompts) == 2  # un second essai a eu lieu
    to, subject, text = stub.mails[0]
    assert to == "a@example.org" and "Semaine prochaine" in text and "Nutrition" in text and "sous-évaluées" in text


def test_digest_uses_the_model_text_when_json_is_valid(ctx):
    from app.coach import notify

    c, uid, repo, llm = ctx
    _digest_setup(repo, uid)
    stub = StubNotifier()
    llm.out = {"subject": "Votre semaine", "intro": "Bravo.", "sections": [{"discipline": "Nutrition", "tips": ["Ajoutez des protéines."]}], "closing": "À dimanche."}
    assert notify.weekly_digest(repo, llm, stub, uid, TODAY) is True
    assert "Ajoutez des protéines." in stub.mails[0][2] and len(llm.prompts) == 1


def test_chat_context_carries_the_nutrition_data_for_food_questions(ctx):
    from datetime import date, timedelta

    c, uid, repo, llm = ctx
    m = repo.add_meal(uid, date.today() - timedelta(days=1), "dîner", "bourguignon 430 g", None)
    repo.set_meal_analysis(uid, m["id"], {"kcal": 720, "protein_g": 45, "carbs_g": 30, "fat_g": 40, "estimated": True})
    llm.out = {"reply": "Votre moyenne est correcte.", "motivation": "ok", "remember": ""}
    assert c.post(f"/users/{uid}/coach/chat", json={"message": "Est-ce que je mange assez de protéines ?"}).status_code == 200
    assert '"nutrition"' in llm.system and "bourguignon" not in llm.system.split('"nutrition"')[0]
    assert "cibles_jour" in llm.system and "sept_jours" in llm.system and "720" in llm.system
    assert "Questions d'alimentation" in llm.system
