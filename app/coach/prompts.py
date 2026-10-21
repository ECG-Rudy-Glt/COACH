"""Prompts du coach par langue : le français est dans le code (service, chat, intake, notify), l'anglais dans `data/prompts/en.yaml`.

Même structure, mêmes clés JSON, mêmes identifiants de règles et noms d'actions dans toutes les langues : seul le texte adressé à l'utilisateur change.
Une langue sans prompt traduit garde le prompt français suivi d'une consigne explicite de langue de réponse, jamais l'inverse (voir docs/prompts.md).
"""
from functools import lru_cache
from pathlib import Path

import yaml

from app import i18n

DIR = Path(__file__).resolve().parent.parent.parent / "data" / "prompts"
MARKER = "LANGUAGE:"


@lru_cache(maxsize=len(i18n.SUPPORTED))
def _load(lang: str) -> dict[str, str]:
    path = DIR / f"{lang}.yaml"
    return yaml.safe_load(path.read_text(encoding="utf-8")) if path.exists() else {}


def language_rule(lang: str) -> str:
    """Consigne de langue de réponse, ajoutée quand le prompt n'est pas écrit dans cette langue."""
    name = i18n.LANG_NAMES.get(lang, lang)
    return f"\n{MARKER} write every text meant for the user in {name}. JSON keys, identifiers, rule ids and action names stay unchanged."


def get(name: str, default: str, lang: str | None = None) -> str:
    """Prompt `name` dans la langue demandée (langue de la requête par défaut) ; `default` est le texte français du code."""
    lang = lang or i18n.current()
    if lang == "fr":
        return default
    return _load(lang).get(name) or default + language_rule(lang)


def with_language(system: str, lang: str | None = None) -> str:
    """Ajoute la consigne de langue à un prompt qui n'en porte pas encore (appel LLM hors coach, ex. l'estimation d'un repas)."""
    lang = lang or i18n.current()
    return system if lang == "fr" or MARKER in system else system + language_rule(lang)
