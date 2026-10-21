import json

import pytest

from app.coach import llm as mod
from app.coach.llm import AnthropicLLM, LLMError, NoLLM, OpenAICompatLLM, is_configured, make_llm


def test_factory(monkeypatch):
    assert isinstance(make_llm("anthropic"), AnthropicLLM)
    assert isinstance(make_llm("openai"), OpenAICompatLLM)
    for p in ("gemini", "mistral", "openrouter", "ollama", "custom"):
        assert isinstance(make_llm(p), OpenAICompatLLM)
    assert isinstance(make_llm("none"), NoLLM)
    with pytest.raises(ValueError):
        make_llm("inconnu")


def test_catalog_is_consistent():
    cat = mod.catalog()
    assert {"anthropic", "openai", "gemini", "mistral", "openrouter", "ollama", "custom", "none"} <= set(cat)
    for name, p in cat.items():
        assert p["kind"] in ("anthropic", "openai", "none"), name
        ids = [m["id"] for m in p["models"]]
        assert len(ids) == len(set(ids)), name
        if p["models"]:
            assert p["model"] in ids and p["fast"] in ids, name


def test_provider_selection_and_models(monkeypatch):
    monkeypatch.setenv("LLM_PROVIDER", "mistral")
    monkeypatch.delenv("LLM_MODEL", raising=False)
    monkeypatch.delenv("LLM_MODEL_FAST", raising=False)
    assert mod.default_model() == "mistral-large-latest" and mod.fast_model() == "mistral-small-latest"
    monkeypatch.setenv("LLM_MODEL", "mon-modele")
    assert mod.default_model() == "mon-modele" and mod.fast_model() == "mon-modele"
    monkeypatch.setenv("LLM_MODEL_FAST", "rapide")
    assert mod.fast_model() == "rapide"
    d = mod.describe()
    assert d["provider"] == "mistral" and "key" not in " ".join(d).replace("key_env", "")
    monkeypatch.setenv("LLM_PROVIDER", "nimporte")
    with pytest.raises(ValueError):
        mod.provider_info()


def test_key_from_secret_file(monkeypatch, tmp_path):
    f = tmp_path / "k"
    f.write_text("secret-value\n")
    monkeypatch.delenv("MISTRAL_API_KEY", raising=False)
    monkeypatch.delenv("LLM_API_KEY", raising=False)
    monkeypatch.setenv("MISTRAL_API_KEY_FILE", str(f))
    assert OpenAICompatLLM("mistral").configured() and OpenAICompatLLM("mistral")._key() == "secret-value"


def test_ollama_is_free_and_keyless(monkeypatch):
    monkeypatch.setenv("LLM_PROVIDER", "ollama")
    monkeypatch.delenv("LLM_PRICE_IN_EUR_PER_MTOK", raising=False)
    assert mod.price_eur(1_000_000, 1_000_000) == 0
    assert OpenAICompatLLM("ollama").configured()


def test_degraded_without_key(monkeypatch):
    monkeypatch.delenv("ANTHROPIC_API_KEY", raising=False)
    monkeypatch.delenv("OPENAI_API_KEY", raising=False)
    monkeypatch.delenv("LLM_API_KEY", raising=False)
    monkeypatch.delenv("LLM_BASE_URL", raising=False)
    for p in (AnthropicLLM(), OpenAICompatLLM("openai"), NoLLM()):
        assert is_configured(p) is False
        with pytest.raises(LLMError):
            p.complete("s", "u", 10)


def test_custom_needs_base_url(monkeypatch):
    monkeypatch.delenv("LLM_API_KEY", raising=False)
    monkeypatch.delenv("LLM_BASE_URL", raising=False)
    assert not OpenAICompatLLM("custom").configured()
    monkeypatch.setenv("LLM_BASE_URL", "http://serveur:8080/v1")
    assert OpenAICompatLLM("custom").configured()


def test_openai_complete_and_tools(monkeypatch):
    monkeypatch.setenv("LLM_PROVIDER", "custom")
    monkeypatch.setenv("LLM_BASE_URL", "http://llm.local/v1")
    monkeypatch.setenv("LLM_MODEL", "petit")
    calls = []
    replies = [
        {"choices": [{"message": {"role": "assistant", "content": None, "tool_calls": [
            {"id": "t1", "type": "function", "function": {"name": "outil", "arguments": json.dumps({"x": 1})}}]}}],
         "usage": {"prompt_tokens": 10, "completion_tokens": 2}},
        {"choices": [{"message": {"role": "assistant", "content": "fini"}}], "usage": {"prompt_tokens": 20, "completion_tokens": 3}},
    ]

    def fake(url, body, headers):
        calls.append((url, body))
        return replies[len(calls) - 1]

    monkeypatch.setattr(mod, "_http_json", fake)
    seen = []
    res = OpenAICompatLLM("custom").converse("sys", "question", 100, None, None,
                                     [{"name": "outil", "description": "d", "input_schema": {"type": "object", "properties": {}}}],
                                     lambda n, a: seen.append((n, a)) or {"ok": True})
    assert res.text == "fini" and (res.input_tokens, res.output_tokens, res.model) == (30, 5, "petit")
    assert seen == [("outil", {"x": 1})]
    assert calls[0][0] == "http://llm.local/v1/chat/completions"
    assert calls[1][1]["messages"][-1] == {"role": "tool", "tool_call_id": "t1", "content": '{"ok": true}'}


def test_openai_image_is_data_url(monkeypatch):
    monkeypatch.setenv("LLM_PROVIDER", "custom")
    monkeypatch.setenv("LLM_BASE_URL", "http://x/v1")
    monkeypatch.setenv("LLM_API_KEY", "k")
    sent = {}
    monkeypatch.setattr(mod, "_http_json", lambda u, b, h: sent.update(b=b, h=h) or {"choices": [{"message": {"content": "{}"}}]})
    OpenAICompatLLM("custom").complete("s", "u", 10, "m", image=("image/jpeg", "QUJD"))
    assert sent["b"]["messages"][-1]["content"][0]["image_url"]["url"] == "data:image/jpeg;base64,QUJD"
    assert sent["h"] == {"authorization": "Bearer k"}


def test_rejects_non_http_scheme(monkeypatch):
    monkeypatch.setenv("LLM_PROVIDER", "custom")
    monkeypatch.setenv("LLM_BASE_URL", "file:///etc")
    with pytest.raises(LLMError):
        OpenAICompatLLM("custom").complete("s", "u", 10, "m")


# ---- mode JSON et repli sans outils (#34) ----
from pathlib import Path  # noqa: E402

FIXTURES = Path(__file__).parent / "fixtures" / "llm"


def sample(name):
    return json.loads((FIXTURES / name).read_text(encoding="utf-8"))


def use(monkeypatch, provider, **env):
    monkeypatch.setenv("LLM_PROVIDER", provider)
    for k in ("LLM_JSON_MODE", "LLM_TOOLS", "LLM_MODEL", "LLM_BASE_URL"):
        monkeypatch.delenv(k, raising=False)
    monkeypatch.setenv("LLM_API_KEY", "k")
    for k, v in env.items():
        monkeypatch.setenv(k, v)


def capture(monkeypatch, replies):
    sent = []

    def fake(url, body, headers):
        sent.append(json.loads(json.dumps(body)))  # copie : l'adaptateur retire parfois une option avant de réessayer
        r = replies[min(len(sent) - 1, len(replies) - 1)]
        if isinstance(r, Exception):
            raise r
        return r

    monkeypatch.setattr(mod, "_http_json", fake)
    return sent


def test_catalog_declares_valid_json_modes():
    for name, p in mod.catalog().items():
        assert p.get("json_mode", "none") in ("json_object", "none"), name
    assert mod.json_mode_kind("openai") == mod.json_mode_kind("mistral") == mod.json_mode_kind("ollama") == "json_object"
    assert mod.json_mode_kind("anthropic") == mod.json_mode_kind("custom") == "none"


@pytest.mark.parametrize("provider,fixture", [("openai", "openai_chat_json.json"), ("mistral", "mistral_chat_json.json"), ("ollama", "ollama_chat_json.json")])
def test_json_mode_is_requested_only_when_asked(monkeypatch, provider, fixture):
    use(monkeypatch, provider)
    sent = capture(monkeypatch, [sample(fixture)])
    res = OpenAICompatLLM(provider).complete("s", "u", 100, "m", json_mode=True)
    assert sent[0]["response_format"] == {"type": "json_object"}
    assert res.input_tokens > 0 and "Semaine régulière" in res.text
    OpenAICompatLLM(provider).complete("s", "u", 100, "m")
    assert "response_format" not in sent[1]  # le chat libre n'en veut pas


def test_json_mode_overrides_and_anthropic_ignores_it(monkeypatch):
    use(monkeypatch, "custom", LLM_BASE_URL="http://x/v1")
    sent = capture(monkeypatch, [sample("openai_chat_json.json")])
    OpenAICompatLLM("custom").complete("s", "u", 10, "m", json_mode=True)
    assert "response_format" not in sent[0]  # serveur inconnu : pas d'option par défaut
    monkeypatch.setenv("LLM_JSON_MODE", "on")
    OpenAICompatLLM("custom").complete("s", "u", 10, "m", json_mode=True)
    assert sent[1]["response_format"] == {"type": "json_object"}
    monkeypatch.setenv("LLM_JSON_MODE", "off")
    OpenAICompatLLM("custom").complete("s", "u", 10, "m", json_mode=True)
    assert "response_format" not in sent[2]
    use(monkeypatch, "anthropic")
    sent = capture(monkeypatch, [sample("anthropic_messages_json.json")])
    res = AnthropicLLM().complete("s", "u", 10, "claude-sonnet-5-5", json_mode=True)
    assert "response_format" not in sent[0] and res.output_tokens == 41


def test_json_mode_refused_by_the_server_falls_back_once(monkeypatch):
    use(monkeypatch, "ollama")
    sent = capture(monkeypatch, [LLMError("Le service IA a répondu 400.", 400), sample("ollama_chat_json.json"), sample("ollama_chat_json.json")])
    llm = OpenAICompatLLM("ollama")
    assert "Semaine" in llm.complete("s", "u", 10, "m", json_mode=True).text
    assert "response_format" in sent[0] and "response_format" not in sent[1]
    llm.complete("s", "u", 10, "m", json_mode=True)
    assert len(sent) == 3 and "response_format" not in sent[2]  # refus mémorisé : plus d'aller-retour inutile
    use(monkeypatch, "ollama")
    capture(monkeypatch, [LLMError("Le service IA a répondu 401.", 401)])
    with pytest.raises(LLMError):  # une autre erreur n'est pas masquée
        OpenAICompatLLM("ollama").complete("s", "u", 10, "m", json_mode=True)


TOOL = [{"name": "search_history", "description": "d", "input_schema": {"type": "object", "properties": {}}}]


def test_model_without_tools_answers_without_history_search(monkeypatch):
    use(monkeypatch, "ollama")
    sent = capture(monkeypatch, [sample("ollama_chat_json.json")])
    seen = []
    res = OpenAICompatLLM("ollama").converse("s", "q", 100, "llama3.2-vision:11b", None, TOOL, lambda n, a: seen.append(n))
    assert "tools" not in sent[0] and seen == [] and res.text  # le catalogue dit tools: false
    assert mod.supports_tools("qwen2.5:7b", "ollama") and not mod.supports_tools("llama3.2-vision:11b", "ollama")
    monkeypatch.setenv("LLM_TOOLS", "off")
    assert not mod.supports_tools("qwen2.5:7b", "ollama")
    monkeypatch.setenv("LLM_TOOLS", "on")
    assert mod.supports_tools("llama3.2-vision:11b", "ollama")


def test_tools_refused_by_the_server_degrade_gracefully(monkeypatch):
    use(monkeypatch, "ollama")
    sent = capture(monkeypatch, [LLMError("Le service IA a répondu 400.", 400), sample("ollama_chat_json.json"), sample("ollama_chat_json.json")])
    llm = OpenAICompatLLM("ollama")
    assert llm.converse("s", "q", 100, "qwen2.5:7b", None, TOOL, lambda n, a: {}).text
    assert "tools" in sent[0] and "tools" not in sent[1]
    llm.converse("s", "q", 100, "qwen2.5:7b", None, TOOL, lambda n, a: {})
    assert len(sent) == 3 and "tools" not in sent[2]


def test_tool_call_sample_still_runs_the_tool(monkeypatch):
    use(monkeypatch, "openai")
    sent = capture(monkeypatch, [sample("openai_tool_call.json"), sample("openai_chat_json.json")])
    seen = []
    res = OpenAICompatLLM("openai").converse("s", "q", 100, "gpt-4o", None, TOOL, lambda n, a: seen.append((n, a)) or {"ok": 1})
    assert seen == [("search_history", {"days": 14})] and "tools" in sent[0] and "Semaine" in res.text


def test_anthropic_tools_can_be_turned_off(monkeypatch):
    use(monkeypatch, "anthropic", LLM_TOOLS="off")
    sent = capture(monkeypatch, [sample("anthropic_messages_json.json")])
    assert AnthropicLLM().converse("s", "q", 100, "claude-sonnet-5-5", None, TOOL, lambda n, a: {}).text
    assert "tools" not in sent[0]


def test_background_calls_ask_for_json():
    """Bilan, notifications et estimation de repas demandent le mode JSON ; le chat libre non."""
    import inspect

    from app.coach import chat, notify, service
    from app.nutrition import analyze

    for module in (service, notify, analyze):
        assert "json_mode=True" in inspect.getsource(module), module.__name__
    assert "json_mode" not in inspect.getsource(chat)


# --- coût estimé : tarif par modèle, conversion USD→EUR, tokens de cache ---

def _clean_price_env(monkeypatch, provider="anthropic"):
    for k in ("LLM_PRICE_IN_EUR_PER_MTOK", "LLM_PRICE_OUT_EUR_PER_MTOK", "LLM_USD_TO_EUR", "LLM_MODEL"):
        monkeypatch.delenv(k, raising=False)
    monkeypatch.setenv("LLM_PROVIDER", provider)


def test_known_model_priced_in_usd_converted_to_eur(monkeypatch):
    _clean_price_env(monkeypatch)
    # Haiku 4.5 : 1 $ en entrée, 5 $ en sortie par million (le suffixe daté de l'identifiant est ignoré)
    assert mod.price_eur(1_000_000, 0, "claude-haiku-4-5-20251001") == pytest.approx(1 * mod.DEFAULT_USD_TO_EUR)
    assert mod.price_eur(0, 1_000_000, "claude-haiku-4-5") == pytest.approx(5 * mod.DEFAULT_USD_TO_EUR)
    assert mod.price_eur(1_000_000, 1_000_000, "claude-sonnet-5-5") == pytest.approx(12 * mod.DEFAULT_USD_TO_EUR)
    monkeypatch.setenv("LLM_USD_TO_EUR", "0.5")
    assert mod.price_eur(1_000_000, 1_000_000, "claude-haiku-4-5-20251001") == pytest.approx(3.0)
    monkeypatch.setenv("LLM_USD_TO_EUR", "pas un nombre")  # valeur illisible : taux par défaut, pas d'erreur
    assert mod.price_eur(1_000_000, 0, "claude-haiku-4-5") == pytest.approx(mod.DEFAULT_USD_TO_EUR)


def test_unknown_model_falls_back_to_legacy_default_never_zero(monkeypatch):
    _clean_price_env(monkeypatch)
    assert mod.price_eur(1_000_000, 1_000_000, "un-modele-inconnu") == pytest.approx(18.0)
    assert mod.price_eur(1_000_000, 1_000_000, None) > 0  # LLM_MODEL absent : modèle par défaut du fournisseur, jamais 0


def test_env_prices_stay_prioritary_each_side_independently(monkeypatch):
    _clean_price_env(monkeypatch)
    monkeypatch.setenv("LLM_PRICE_IN_EUR_PER_MTOK", "2")
    assert mod.price_eur(1_000_000, 1_000_000, "claude-haiku-4-5") == pytest.approx(2 + 5 * mod.DEFAULT_USD_TO_EUR)  # seule l'entrée est forcée
    monkeypatch.setenv("LLM_PRICE_OUT_EUR_PER_MTOK", "7")
    assert mod.price_eur(1_000_000, 1_000_000, "claude-haiku-4-5") == pytest.approx(9.0)
    monkeypatch.setenv("LLM_PRICE_IN_EUR_PER_MTOK", "")  # variable vide (docker compose `${VAR:-}`) = non définie
    assert mod.price_eur(1_000_000, 0, "claude-haiku-4-5") == pytest.approx(mod.DEFAULT_USD_TO_EUR)


def test_local_model_stays_free_even_with_known_name(monkeypatch):
    _clean_price_env(monkeypatch, "ollama")
    assert mod.price_eur(1_000_000, 1_000_000, "claude-haiku-4-5") == 0


def test_cache_tokens_priced_at_cache_rates(monkeypatch):
    _clean_price_env(monkeypatch)
    rate = mod.DEFAULT_USD_TO_EUR
    # 1 M de tokens d'entrée : 300 k au tarif plein, 600 k lus (0,1 ×), 100 k écrits (1,25 ×)
    got = mod.price_eur(1_000_000, 0, "claude-haiku-4-5", cache_read=600_000, cache_write=100_000)
    assert got == pytest.approx((0.3 + 0.6 * 0.1 + 0.1 * 1.25) * rate)
    # Fable 5.1 : lecture à 0,25 $ pour 10 $ (0,025 ×), Opus 5.5 : 0,20 $ pour 4 $ (0,05 ×)
    assert mod.price_eur(1_000_000, 0, "claude-fable-5-1", cache_read=1_000_000) == pytest.approx(0.25 * rate)
    assert mod.price_eur(1_000_000, 0, "claude-opus-5-5", cache_read=1_000_000) == pytest.approx(0.20 * rate)
    # le cache suit aussi le prix d'entrée forcé par l'environnement ; modèle inconnu : 0,1 ×
    monkeypatch.setenv("LLM_PRICE_IN_EUR_PER_MTOK", "10")
    assert mod.price_eur(1_000_000, 0, "inconnu", cache_read=1_000_000) == pytest.approx(1.0)
    assert mod.price_eur(100, 0, "inconnu", cache_read=10_000_000) >= 0  # sous-ensemble incohérent : borné, jamais négatif


def test_anthropic_usage_counts_cache_and_result_is_priced(monkeypatch):
    _clean_price_env(monkeypatch)
    monkeypatch.setenv("ANTHROPIC_API_KEY", "test")
    usage = {"input_tokens": 100, "cache_read_input_tokens": 9000, "cache_creation_input_tokens": 500, "output_tokens": 200}
    assert mod.anthropic_usage(usage) == (9600, 200, 9000, 500)
    seen = []

    def fake_post(self, body):
        seen.append(body)
        return {"content": [{"type": "text", "text": "ok"}], "usage": usage}

    monkeypatch.setattr(AnthropicLLM, "_post", fake_post)
    res = AnthropicLLM().complete("s", "u", 10, "claude-haiku-4-5-20251001")
    assert (res.input_tokens, res.output_tokens, res.cache_read_tokens, res.cache_write_tokens) == (9600, 200, 9000, 500)
    expected = ((100 + 9000 * 0.1 + 500 * 1.25) * 1 + 200 * 5) / 1_000_000 * mod.DEFAULT_USD_TO_EUR
    assert mod.price_result(res) == pytest.approx(expected)
    plain = mod.LLMResult("x", 1_000_000, 0, "claude-haiku-4-5")  # fournisseur sans cache : champs à 0
    assert mod.price_result(plain) == pytest.approx(mod.DEFAULT_USD_TO_EUR)
