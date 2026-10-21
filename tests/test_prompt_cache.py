"""Cache de prompt Anthropic : le préfixe fixe (consigne, règles, sources) porte `cache_control`, le contexte de l'utilisateur jamais."""
import json
from datetime import date, timedelta

import pytest
from fastapi.testclient import TestClient

from app.coach import chat as chat_mod
from app.coach import llm as mod
from app.coach import notify, prompts, service
from app.coach.llm import AnthropicLLM, CachedSystem, OpenAICompatLLM
from app.main import app, get_repo
from app.repo import MemoryRepo

PW = "un-mot-de-passe-solide"
TODAY = date.today()
REPLY = {"reply": "Bien reçu.", "motivation": "ok", "remember": ""}
USAGE = {"input_tokens": 120, "cache_creation_input_tokens": 6000, "cache_read_input_tokens": 0, "output_tokens": 80}


class FakeAnthropic:
    """Remplace l'appel HTTP : garde les corps de requête envoyés à l'API Messages et répond avec un JSON valide."""

    def __init__(self, monkeypatch, text=None, usage=None):
        self.bodies: list[dict] = []
        self.text, self.usage = json.dumps(text or REPLY), usage or USAGE
        monkeypatch.setattr(mod, "_http_json", self.post)

    def post(self, url, body, headers):
        self.bodies.append(json.loads(json.dumps(body)))  # copie profonde, ce que l'API recevrait réellement
        return {"content": [{"type": "text", "text": self.text}], "usage": self.usage}


def marked(node, path="body"):
    """Chemins de tous les `cache_control` d'un corps de requête."""
    if isinstance(node, dict):
        return [f"{path}.cache_control"] * ("cache_control" in node) + [m for k, v in node.items() for m in marked(v, f"{path}.{k}")]
    if isinstance(node, list):
        return [m for i, v in enumerate(node) for m in marked(v, f"{path}[{i}]")]
    return []


@pytest.fixture(autouse=True)
def _env(monkeypatch):
    monkeypatch.setenv("LLM_PROVIDER", "anthropic")
    monkeypatch.setenv("ANTHROPIC_API_KEY", "test")
    for k in ("LLM_PROMPT_CACHE", "LLM_MODEL", "LLM_PRICE_IN_EUR_PER_MTOK", "LLM_PRICE_OUT_EUR_PER_MTOK", "LLM_USD_TO_EUR", "LLM_TOOLS", "LLM_BASE_URL"):
        monkeypatch.delenv(k, raising=False)


def test_cached_system_is_a_plain_string_with_two_parts():
    s = CachedSystem("FIXE", " variable")
    assert s == "FIXE variable" and s.fixed == "FIXE" and s.variable == " variable" and "variable" in s
    t = s + "\nLANGUAGE: x"  # un ajout reste après le préfixe
    assert isinstance(t, CachedSystem) and t.fixed == "FIXE" and t.variable == " variable\nLANGUAGE: x"
    assert prompts.with_language(s, "en").fixed == "FIXE"


def test_marker_goes_on_the_fixed_block_only(monkeypatch):
    api = FakeAnthropic(monkeypatch)
    res = AnthropicLLM().complete(CachedSystem("PRÉFIXE FIXE", "\n\nCONTEXTE :\n{}"), "Bonjour", 50, "claude-haiku-4-5-20251001", history=[{"role": "user", "content": "avant"}])
    body = api.bodies[0]
    assert body["system"] == [{"type": "text", "text": "PRÉFIXE FIXE", "cache_control": {"type": "ephemeral"}}, {"type": "text", "text": "\n\nCONTEXTE :\n{}"}]
    assert marked(body) == ["body.system[0].cache_control"]  # ni l'historique, ni le message, ni le contexte
    assert (res.input_tokens, res.cache_write_tokens, res.cache_read_tokens) == (6120, 6000, 0)


def test_other_cases_keep_the_old_payload(monkeypatch):
    api = FakeAnthropic(monkeypatch)
    llm = AnthropicLLM()
    llm.complete("simple texte", "u", 10, "m")  # une str ordinaire (repas, accueil) : inchangé
    llm.complete(CachedSystem("seul préfixe"), "u", 10, "m")  # pas de partie variable : un seul bloc
    monkeypatch.setenv("LLM_PROMPT_CACHE", "off")  # interrupteur : un seul bloc de texte, comme avant
    llm.complete(CachedSystem("PRÉFIXE", " suite"), "u", 10, "m")
    assert api.bodies[0]["system"] == "simple texte" and not marked(api.bodies[0])
    assert api.bodies[1]["system"] == [{"type": "text", "text": "seul préfixe", "cache_control": {"type": "ephemeral"}}]
    assert api.bodies[2]["system"] == "PRÉFIXE suite" and not marked(api.bodies[2])


def test_language_rule_comes_after_the_cached_prefix(monkeypatch):
    api = FakeAnthropic(monkeypatch)
    monkeypatch.setattr("app.i18n.current", lambda: "es")
    AnthropicLLM().complete(CachedSystem("PRÉFIXE", "\n\nCONTEXTE :\nx"), "u", 10, "m")
    first, second = api.bodies[0]["system"]
    assert first["text"] == "PRÉFIXE" and "LANGUAGE:" not in first["text"] and second["text"].startswith("\n\nCONTEXTE :") and "LANGUAGE:" in second["text"]


def test_converse_marks_the_prefix_on_every_round_and_sums_cache_tokens(monkeypatch):
    calls = iter([{"content": [{"type": "tool_use", "id": "t1", "name": "x", "input": {}}], "usage": {"input_tokens": 50, "cache_creation_input_tokens": 6000, "output_tokens": 10}},
                  {"content": [{"type": "text", "text": "{}"}], "usage": {"input_tokens": 80, "cache_read_input_tokens": 6000, "output_tokens": 20}}])
    bodies = []

    def post(url, body, headers):
        bodies.append(json.loads(json.dumps(body)))
        return next(calls)

    monkeypatch.setattr(mod, "_http_json", post)
    tools = [{"name": "x", "description": "d", "input_schema": {"type": "object", "properties": {}}}]
    res = AnthropicLLM().converse(CachedSystem("PRÉFIXE", " suite"), "question", 50, "claude-haiku-4-5", [], tools, lambda n, a: {"ok": 1})
    assert len(bodies) == 2
    for b in bodies:
        assert b["system"][0] == {"type": "text", "text": "PRÉFIXE", "cache_control": {"type": "ephemeral"}}
        assert marked(b) == ["body.system[0].cache_control"] and b["tools"][0].get("cache_control") is None  # un seul marqueur : il couvre aussi les outils, rendus avant lui
    assert bodies[0]["system"] == bodies[1]["system"]
    assert (res.input_tokens, res.output_tokens, res.cache_write_tokens, res.cache_read_tokens) == (12130, 30, 6000, 6000)


def test_openai_compatible_providers_are_unchanged(monkeypatch):
    sent = []
    answer = {"choices": [{"message": {"content": "{}"}}], "usage": {"prompt_tokens": 9, "completion_tokens": 3}}
    monkeypatch.setattr(mod, "_http_json", lambda url, body, headers: sent.append(json.loads(json.dumps(body))) or answer)
    monkeypatch.setenv("OPENAI_API_KEY", "test")
    res = OpenAICompatLLM("openai").complete(CachedSystem("PRÉFIXE", " suite"), "u", 10, "gpt-x")
    assert sent[0]["messages"][0] == {"role": "system", "content": "PRÉFIXE suite"} and not marked(sent[0])
    assert (res.input_tokens, res.cache_read_tokens, res.cache_write_tokens) == (9, 0, 0)


@pytest.fixture
def client(monkeypatch):
    from app.auth import reset_rate_limits

    reset_rate_limits()
    repo = MemoryRepo()
    app.dependency_overrides[get_repo] = lambda: repo
    old = app.state.llm
    app.state.llm = AnthropicLLM()
    c = TestClient(app)
    uid = c.post("/auth/register", json={"name": "Prénom-secret", "email": "secret@example.org", "password": PW}).json()["id"]
    yield c, uid, repo
    app.state.llm = old
    app.dependency_overrides.clear()


def test_chat_sends_a_stable_fixed_prefix_then_the_user_context(client, monkeypatch):
    c, uid, repo = client
    api = FakeAnthropic(monkeypatch)
    repo.add_facts(uid, [__import__("app.questionnaire.models", fromlist=["Fact"]).Fact(key="body.weight_kg", value=71.5)])
    assert c.post(f"/users/{uid}/coach/chat", json={"message": "Premier message"}).status_code == 200
    repo.add_memory(uid, "decision", (TODAY, TODAY), "Dort 5 h par nuit", {})
    assert c.post(f"/users/{uid}/coach/chat", json={"message": "Second message"}).status_code == 200
    first, second = api.bodies
    for b in (first, second):
        fixed, variable = b["system"]
        assert marked(b) == ["body.system[0].cache_control"] and "cache_control" not in variable
        assert fixed["text"].startswith("Tu es le coach") and '"regles"' in fixed["text"] and '"sources"' in fixed["text"] and "G1" in fixed["text"]
        assert variable["text"].startswith("\n\nCONTEXTE :\n") and '"aujourdhui"' in variable["text"] and '"regles"' not in variable["text"] and '"sources"' not in variable["text"]
        for private in ("Prénom-secret", "secret@example.org", "71.5", TODAY.isoformat(), "Dort 5 h"):
            assert private not in fixed["text"]  # aucun horodatage ni donnée de l'utilisateur dans le préfixe
    assert first["system"][0] == second["system"][0]  # octet pour octet identique d'un message à l'autre : c'est ce qui permet la relecture du cache
    assert first["system"][1] != second["system"][1] and "Dort 5 h" in second["system"][1]["text"]
    assert [t["name"] for t in first["tools"]] == [t["name"] for t in second["tools"]] and not any("cache_control" in t for t in first["tools"])
    assert len(second["messages"]) > 1 and second["messages"][-1] == {"role": "user", "content": "Second message"}


def test_chat_prefix_is_large_enough_for_the_smallest_cache_minimum():
    """Haiku 4.5 ne met en cache qu'à partir de 4 096 tokens : le préfixe naturel (consigne + règles + sources) doit les dépasser sans remplissage."""
    from app import evidence

    digest = evidence.digest(evidence.load_evidence(service.ROOT / "data" / "evidence", set(service.rules())))  # les vraies sources, quel que soit l'état du processus de test
    refs, _ = service.split_context({"regles": service.rules(), "sources": digest})
    # estimation prudente : un token pour 4 caractères au moins (le français et le JSON en donnent plutôt 3 à 3,5)
    assert len(chat_mod.CHAT_SYSTEM + service.SOURCES_RULE + refs) / 4 > 4096
    assert len(service.SYSTEM + refs) / 4 > 4096


def test_review_moves_rules_and_sources_into_the_system_prefix(client, monkeypatch):
    c, uid, repo = client
    api = FakeAnthropic(monkeypatch, text={"summary": "ok", "adherence": "", "questions": [], "proposals": []})
    assert c.post(f"/users/{uid}/coach/review").status_code == 200
    body = api.bodies[0]
    assert len(body["system"]) == 1 and body["system"][0]["cache_control"] == {"type": "ephemeral"} and marked(body) == ["body.system[0].cache_control"]
    assert '"regles"' in body["system"][0]["text"] and "Prénom-secret" not in body["system"][0]["text"]
    user = body["messages"][-1]["content"]
    assert '"seances_a_venir"' in user and '"regles"' not in user and '"sources"' not in user


def test_digest_and_checkin_use_the_same_split(client, monkeypatch):
    c, uid, repo = client
    api = FakeAnthropic(monkeypatch, text={"subject": "S", "intro": "i", "sections": [{"discipline": "Nutrition", "tips": ["t"]}], "closing": "c"})
    repo.set_prefs(uid, {"email_enabled": True, "email": "a@example.org", "push_enabled": False, "ntfy_topic": ""})
    repo.add_facts(uid, [__import__("app.questionnaire.models", fromlist=["Fact"]).Fact(key="sports.practiced", value=["running"])])

    class Mail:
        def email(self, *a):
            pass

    assert notify.weekly_digest(repo, app.state.llm, Mail(), uid, TODAY)
    body = api.bodies[0]
    assert marked(body) == ["body.system[0].cache_control"] and '"regles"' in body["system"][0]["text"]
    assert '"disciplines"' in body["messages"][-1]["content"] and '"regles"' not in body["messages"][-1]["content"]


def test_split_context_moves_fields_without_dropping_any():
    ctx = {"aujourdhui": "x", "profil": {}, "regles": {"G1": "r"}, "sources": {"RUN-001": "s"}, "nutrition": {}}
    refs, rest = service.split_context(ctx)
    assert set(rest) == {"aujourdhui", "profil", "nutrition"}
    assert '"G1": "r"' in refs and '"RUN-001": "s"' in refs and refs.startswith("\n\nRÉFÉRENCES FIXES")
    assert service.split_context({"aujourdhui": "x"})[1] == {"aujourdhui": "x"}


def test_yesterday_and_tomorrow_do_not_change_the_prefix(client, monkeypatch):
    """Le préfixe est le même quel que soit le jour : aucune date n'y entre."""
    c, uid, repo = client
    api = FakeAnthropic(monkeypatch)
    from app.coach import chat

    chat.chat(repo, app.state.llm, uid, "a", TODAY)
    chat.chat(repo, app.state.llm, uid, "b", TODAY + timedelta(days=3))
    assert api.bodies[0]["system"][0] == api.bodies[1]["system"][0]
