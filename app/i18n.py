"""Langue de l'application côté serveur : choix de la langue d'une requête et traduction des textes produits par le serveur.

Le français est la langue source : le texte français sert de clé. `app/static/i18n/<langue>.json` associe chaque texte (ou modèle à trous
« Dans {n} semaines ») à sa traduction ; le même fichier sert à l'interface (`app/static/i18n.js`) et au serveur (notifications, mails).
Un texte sans traduction reste en français. Voir docs/i18n.md.
"""
import json
import os
import re
from collections.abc import Iterator
from contextlib import contextmanager
from contextvars import ContextVar
from functools import lru_cache
from pathlib import Path
from typing import Any

SUPPORTED = ("fr", "en")
STATIC = Path(__file__).resolve().parent / "static" / "i18n"
LANG_NAMES = {"fr": "français", "en": "English"}
_HOLE = re.compile(r"\{(\w+)\}")
_GROUP = {"v": "(.*?)", "num": r"(\d+(?:[.,]\d+)?)"}  # {v} : suffixe facultatif (« s » du pluriel) ; {num}, {num2}… : un nombre seulement

_STRONG = re.compile(r"([.!?;]\s+|\s·\s|\s—\s|\n+)")
_WEAK = re.compile(r"(,\s+|\s\+\s)")

_current: ContextVar[str | None] = ContextVar("lang", default=None)


def normalize(value: str | None) -> str | None:
    """`en`, `en-GB`, `EN_us` -> `en` ; None si la langue n'est pas gérée."""
    short = (value or "").strip().lower().replace("_", "-").split("-")[0]
    return short if short in SUPPORTED else None


def default_lang() -> str:
    """Langue du serveur (`LOCALE`), français si absente ou inconnue."""
    return normalize(os.environ.get("LOCALE")) or "fr"


def from_accept_language(header: str | None) -> str | None:
    """Première langue gérée d'un en-tête `Accept-Language` (l'ordre du navigateur fait foi)."""
    for part in (header or "").split(","):
        found = normalize(part.split(";")[0])
        if found:
            return found
    return None


def resolve(explicit: str | None = None, header: str | None = None, accept: str | None = None) -> str:
    """Langue d'une requête : paramètre `lang` ou en-tête `X-Lang` (choix de l'interface), puis `Accept-Language`, puis `LOCALE`."""
    return normalize(explicit) or normalize(header) or from_accept_language(accept) or default_lang()


def set_current(lang: str | None) -> Any:
    return _current.set(lang)


def reset_current(token: Any) -> None:
    _current.reset(token)


@contextmanager
def use(lang: str | None) -> Iterator[None]:
    """Fixe la langue le temps d'un bloc (tâches de fond : notifications, mails)."""
    token = _current.set(normalize(lang) or default_lang())
    try:
        yield
    finally:
        _current.reset(token)


def current() -> str:
    """Langue de la requête en cours (posée par le middleware), sinon celle du serveur."""
    return _current.get() or default_lang()


class Dictionary:
    """Dictionnaire d'une langue : correspondance exacte, puis modèles à trous du plus précis au plus général (même algorithme que i18n.js)."""

    def __init__(self, entries: dict[str, str]) -> None:
        self.exact = {k: v for k, v in entries.items() if isinstance(v, str)}
        self.patterns: list[tuple[re.Pattern[str], list[str], str, int]] = []
        for fr, tr in self.exact.items():
            names = _HOLE.findall(fr)
            if not names:
                continue
            src = _HOLE.sub(lambda m: _GROUP.get("num" if re.fullmatch(r"num\d*", m.group(1)) else m.group(1), "(.+?)"), re.escape(fr).replace(r"\{", "{").replace(r"\}", "}"))
            self.patterns.append((re.compile("^" + src + "$", re.S), names, tr, len(_HOLE.sub("", fr))))
        self.patterns.sort(key=lambda p: -p[3])
        self._cache: dict[str, str] = {}

    def lookup(self, text: str) -> str:
        hit = self.exact.get(text)
        if hit is not None:
            return hit
        if text in self._cache:
            return self._cache[text]
        out = self.lookup_pattern(text)
        if out is None:
            out = self._by_sentence(text)
        self._cache[text] = out
        return out

    def _by_sentence(self, text: str, rx: re.Pattern[str] = _STRONG) -> str:
        """Texte composé de plusieurs phrases ou segments : chaque morceau connu est traduit, le reste reste tel quel.

        Séparateurs forts d'abord (point, « · », tiret long, retour à la ligne) ; un morceau inconnu est redécoupé aux virgules et aux « + » (listes d'exercices)."""
        parts = rx.split(text)
        if len(parts) < 3:
            return text
        out, changed = [], False
        for i in range(0, len(parts), 2):
            seg, sep = parts[i], parts[i + 1] if i + 1 < len(parts) else ""
            punct = sep[:1] if sep[:1] in ".!?;" else ""
            tr = self.exact.get(seg + punct) or self.lookup_pattern(seg + punct)
            if tr is None:
                tr = self.exact.get(seg) or self.lookup_pattern(seg)
                tr = tr + punct if tr is not None else None
            if tr is None and rx is _STRONG:
                weak = self._by_sentence(seg, _WEAK)
                tr = weak + punct if weak != seg else None
            changed = changed or tr is not None
            out += [tr if tr is not None else seg + punct, sep[len(punct):]]
        return "".join(out) if changed else text

    def lookup_pattern(self, text: str) -> str | None:
        for rx, names, tr, _ in self.patterns:
            m = rx.match(text)
            if m:
                return self._fill(tr, names, m.groups())
        return None

    def _fill(self, tr: str, names: list[str], groups: tuple[str, ...]) -> str:
        return _HOLE.sub(lambda h: self.lookup(groups[names.index(h.group(1))]) if h.group(1) in names else "", tr)


@lru_cache(maxsize=len(SUPPORTED))
def dictionary(lang: str) -> Dictionary:
    path = STATIC / f"{lang}.json"
    return Dictionary(json.loads(path.read_text(encoding="utf-8")) if lang != "fr" and path.exists() else {})


def tr(text: str, lang: str | None = None, **values: Any) -> str:
    """Traduit un texte français (ou un modèle à trous) puis remplit les trous ; français inchangé."""
    lang = lang or current()
    out = text if lang == "fr" else dictionary(lang).lookup(text)
    return _HOLE.sub(lambda m: str(values[m.group(1)]) if m.group(1) in values else m.group(0), out) if values else out
