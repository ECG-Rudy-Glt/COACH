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
