"""Appel au LLM isolé derrière un fournisseur interchangeable : mesuré, borné, jamais en boucle.

`LLM_PROVIDER` choisit une entrée de `data/llm_providers.yaml` (anthropic par défaut, openai, gemini, mistral, openrouter, ollama,
custom pour tout serveur compatible OpenAI, none pour désactiver l'IA : le plan, la nutrition et le suivi fonctionnent, seuls le coach,
le chat et l'estimation des repas sont alors inactifs). `LLM_MODEL` fixe le modèle, `LLM_MODEL_FAST` celui des tâches courtes.
"""
import json
import os
import urllib.error
import urllib.request
from dataclasses import dataclass
from functools import lru_cache
from pathlib import Path
from typing import Any

import yaml

from app.config import env

CATALOG_FILE = Path(os.environ.get("LLM_CATALOG", Path(__file__).resolve().parent.parent.parent / "data" / "llm_providers.yaml"))


class LLMError(Exception):
    pass


@dataclass
class LLMResult:
    text: str
    input_tokens: int
    output_tokens: int
    model: str


@lru_cache(maxsize=1)
def catalog() -> dict[str, dict[str, Any]]:
    data = yaml.safe_load(CATALOG_FILE.read_text(encoding="utf-8"))
    return {k: dict(v) for k, v in data["providers"].items()}


def provider_name() -> str:
    return os.environ.get("LLM_PROVIDER", "anthropic").strip().lower() or "anthropic"


def provider_info(name: str | None = None) -> dict[str, Any]:
    name = name or provider_name()
    try:
        return catalog()[name]
    except KeyError:
        raise ValueError(f"LLM_PROVIDER inconnu : {name!r} ({', '.join(catalog())}).") from None


def default_model(fallback: str | None = None) -> str:
    """Modèle choisi par `LLM_MODEL`, sinon `fallback`, sinon le modèle par défaut du fournisseur."""
    return env("LLM_MODEL") or fallback or str(provider_info().get("model", ""))


def fast_model() -> str:
    """Modèle économique pour les tâches courtes (estimation d'un repas) : `LLM_MODEL_FAST`, sinon celui du fournisseur."""
    info = provider_info()
    return env("LLM_MODEL_FAST") or env("LLM_MODEL") or str(info.get("fast") or info.get("model", ""))


def price_eur(input_tokens: int, output_tokens: int) -> float:
    """Estimation du coût (€) pour le plafond mensuel ; tarifs réglables par l'environnement (0 par défaut pour un modèle local)."""
    free = bool(provider_info().get("free"))
    pin = float(os.environ.get("LLM_PRICE_IN_EUR_PER_MTOK", "0" if free else "3"))
    pout = float(os.environ.get("LLM_PRICE_OUT_EUR_PER_MTOK", "0" if free else "15"))
    return (input_tokens * pin + output_tokens * pout) / 1_000_000


def describe() -> dict[str, Any]:
    """État du fournisseur pour l'API : jamais de clé, seulement ce qui aide à choisir."""
    info = provider_info()
    return {"provider": provider_name(), "label": info.get("label"), "model": default_model(), "fast_model": fast_model(),
            "models": info.get("models", []), "key_env": info.get("key_env"), "free": bool(info.get("free")),
            "providers": [{"id": k, "label": v.get("label")} for k, v in catalog().items()]}


def _http_json(url: str, body: dict[str, Any], headers: dict[str, str]) -> dict[str, Any]:
    if not url.startswith(("https://", "http://")):
        raise LLMError("Adresse du service IA invalide.")
    req = urllib.request.Request(url, data=json.dumps(body).encode(), method="POST", headers={"content-type": "application/json", **headers})
    try:
        with urllib.request.urlopen(req, timeout=90) as r:  # noqa: S310 : schéma http(s) vérifié, adresse fixée par l'administrateur
            return json.load(r)  # type: ignore[no-any-return]
    except urllib.error.HTTPError as e:
        raise LLMError(f"Le service IA a répondu {e.code}.") from e
    except (urllib.error.URLError, TimeoutError, ValueError) as e:
        raise LLMError("Le service IA est injoignable.") from e


def is_configured(llm: Any) -> bool:
    """Vrai si le fournisseur peut répondre (clé présente, ou serveur local déclaré)."""
    check = getattr(llm, "configured", None)
    return bool(check()) if callable(check) else True


class NoLLM:
    """Fonctionnement dégradé : aucun fournisseur d'IA."""

    def configured(self) -> bool:
        return False

    def complete(self, system: str, user: str, max_tokens: int, model: str | None = None, history: list[dict[str, str]] | None = None,
                 image: tuple[str, str] | None = None) -> LLMResult:
        raise LLMError("Aucun fournisseur d'IA n'est configuré sur ce serveur.")


class AnthropicLLM:
    def _key(self) -> str:
        return env("ANTHROPIC_API_KEY") or env("LLM_API_KEY")

    def configured(self) -> bool:
        return bool(self._key())

    def _post(self, body: dict[str, Any]) -> dict[str, Any]:
        key = self._key()
        if not key:
            raise LLMError("Clé Anthropic non configurée sur ce serveur.")
        url = env("LLM_BASE_URL") or str(provider_info("anthropic")["base_url"])
        return _http_json(url, body, {"x-api-key": key, "anthropic-version": "2023-06-01"})

    def converse(self, system: str, user: str, max_tokens: int, model: str | None, history: list[dict[str, str]] | None,
                 tools: list[dict[str, Any]], run_tool: Any, max_rounds: int = 3) -> LLMResult:
        """Échange avec outils de lecture : le modèle demande une recherche, le serveur l'exécute (bornée), puis le modèle conclut."""
        model = model or default_model()
        messages: list[dict[str, Any]] = [*(history or []), {"role": "user", "content": user}]
        tin = tout = 0
        for rnd in range(max_rounds + 1):
            d = self._post({"model": model, "max_tokens": max_tokens, "system": system, "messages": messages, **({"tools": tools} if rnd < max_rounds else {})})
            u = d.get("usage", {})
            tin, tout = tin + int(u.get("input_tokens", 0)), tout + int(u.get("output_tokens", 0))
            blocks = d.get("content", [])
            calls = [b for b in blocks if b.get("type") == "tool_use"]
            if not calls or rnd == max_rounds:
                return LLMResult("".join(b.get("text", "") for b in blocks if b.get("type") == "text"), tin, tout, model)
            messages.append({"role": "assistant", "content": blocks})
            messages.append({"role": "user", "content": [{"type": "tool_result", "tool_use_id": c["id"],
                                                          "content": json.dumps(run_tool(c["name"], c.get("input") or {}), ensure_ascii=False, default=str)[:6000]} for c in calls]})
        return LLMResult("", tin, tout, model)  # inatteignable

    def complete(self, system: str, user: str, max_tokens: int, model: str | None = None, history: list[dict[str, str]] | None = None,
                 image: tuple[str, str] | None = None) -> LLMResult:
        model = model or default_model()
        content: Any = user if not image else [
            {"type": "image", "source": {"type": "base64", "media_type": image[0], "data": image[1]}}, {"type": "text", "text": user}]
        d = self._post({"model": model, "max_tokens": max_tokens, "system": system,
                        "messages": [*(history or []), {"role": "user", "content": content}]})
        text = "".join(b.get("text", "") for b in d.get("content", []) if b.get("type") == "text")
        u = d.get("usage", {})
        return LLMResult(text, int(u.get("input_tokens", 0)), int(u.get("output_tokens", 0)), model)


class OpenAICompatLLM:
    """API « chat completions » : OpenAI, Gemini, Mistral, OpenRouter, Ollama et tout serveur compatible."""

    def __init__(self, provider: str = "openai") -> None:
        self.provider = provider

    def _info(self) -> dict[str, Any]:
        return provider_info(self.provider)

    def _base(self) -> str:
        return (env("LLM_BASE_URL") or str(self._info().get("base_url", ""))).rstrip("/")

    def _key(self) -> str:
        info = self._info()
        return env(str(info.get("key_env") or "LLM_API_KEY")) or env("LLM_API_KEY")

    def configured(self) -> bool:
        # une adresse est indispensable ; la clé l'est sauf pour un serveur local (Ollama…)
        return bool(self._base()) and (bool(self._key()) or not self._info().get("key_required"))

    def _post(self, body: dict[str, Any]) -> dict[str, Any]:
        if not self.configured():
            raise LLMError("Service IA non configuré sur ce serveur (clé ou adresse manquante).")
        key = self._key()
        return _http_json(f"{self._base()}/chat/completions", body, {"authorization": f"Bearer {key}"} if key else {})

    @staticmethod
    def _message(d: dict[str, Any]) -> dict[str, Any]:
        try:
            return d["choices"][0]["message"]  # type: ignore[no-any-return]
        except (KeyError, IndexError, TypeError) as e:
            raise LLMError("Réponse du service IA illisible.") from e

    def complete(self, system: str, user: str, max_tokens: int, model: str | None = None, history: list[dict[str, str]] | None = None,
                 image: tuple[str, str] | None = None) -> LLMResult:
        model = model or default_model()
        content: Any = user if not image else [
            {"type": "image_url", "image_url": {"url": f"data:{image[0]};base64,{image[1]}"}}, {"type": "text", "text": user}]
        d = self._post({"model": model, "max_tokens": max_tokens,
                        "messages": [{"role": "system", "content": system}, *(history or []), {"role": "user", "content": content}]})
        u = d.get("usage", {})
        return LLMResult(str(self._message(d).get("content") or ""), int(u.get("prompt_tokens", 0)), int(u.get("completion_tokens", 0)), model)

    def converse(self, system: str, user: str, max_tokens: int, model: str | None, history: list[dict[str, str]] | None,
                 tools: list[dict[str, Any]], run_tool: Any, max_rounds: int = 3) -> LLMResult:
        model = model or default_model()
        fn = [{"type": "function", "function": {"name": t["name"], "description": t["description"], "parameters": t["input_schema"]}} for t in tools]
        messages: list[dict[str, Any]] = [{"role": "system", "content": system}, *(history or []), {"role": "user", "content": user}]
        tin = tout = 0
        for rnd in range(max_rounds + 1):
            d = self._post({"model": model, "max_tokens": max_tokens, "messages": messages, **({"tools": fn} if rnd < max_rounds else {})})
            u = d.get("usage", {})
            tin, tout = tin + int(u.get("prompt_tokens", 0)), tout + int(u.get("completion_tokens", 0))
            msg = self._message(d)
            calls = msg.get("tool_calls") or []
            if not calls or rnd == max_rounds:
                return LLMResult(str(msg.get("content") or ""), tin, tout, model)
            messages.append(msg)
            for c in calls:
                try:
                    args = json.loads(c["function"].get("arguments") or "{}")
                except ValueError:
                    args = {}
                out = json.dumps(run_tool(c["function"]["name"], args if isinstance(args, dict) else {}), ensure_ascii=False, default=str)[:6000]
                messages.append({"role": "tool", "tool_call_id": c["id"], "content": out})
        return LLMResult("", tin, tout, model)  # inatteignable


def make_llm(provider: str | None = None) -> Any:
    name = (provider or provider_name()).strip().lower()
    kind = provider_info(name).get("kind")
    if kind == "anthropic":
        return AnthropicLLM()
    if kind == "openai":
        return OpenAICompatLLM(name)
    if kind == "none":
        return NoLLM()
    raise ValueError(f"Type de fournisseur inconnu pour {name!r} : {kind!r}.")
