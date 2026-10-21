"""Blessures déclarées en texte libre : normalisation vers les zones connues du moteur (règles S2, S7).

Le menu propose des zones, mais l'utilisateur peut écrire autre chose (« autre », détail libre, anglais, pluriel, accents, majuscules).
La normalisation ne lève jamais d'exception : une valeur inutilisable est ignorée, un texte non reconnu est rendu tel quel pour être signalé.
"""
from __future__ import annotations

import re
import unicodedata
from typing import Any

# zone canonique -> mots (sans accent, minuscules) ; un pluriel en « s » ou « x » est accepté
ZONE_WORDS: dict[str, tuple[str, ...]] = {
    "genou": ("genou", "knee", "rotule", "rotulien", "rotulienne", "patella", "patellar", "patellaire", "menisque", "meniscus", "essuie-glace", "iliotibial", "itb", "lca", "acl"),
    "cheville": ("cheville", "ankle"),
    "hanche": ("hanche", "hip", "hips"),
    "dos": ("dos", "lombaire", "lombalgie", "back", "lumbar", "sciatique", "sciatica", "cervicale", "spine", "colonne"),
    "épaule": ("epaule", "shoulder", "coiffe", "rotator", "deltoide"),
    "tendon d'Achille": ("achille", "achilles", "tendon d'achille", "achilles tendon", "tendon d achille"),
    "tibia": ("tibia", "shin", "periostite", "shin splints"),
    "coude": ("coude", "elbow", "epicondylite"),
    "poignet": ("poignet", "wrist"),
    "mollet": ("mollet", "calf", "calves"),
    "pied": ("pied", "foot", "feet", "plantaire", "plantar", "fascia", "voute", "talon", "heel", "metatarse"),
    "ischio-jambiers": ("ischio", "ischio-jambier", "ischio-jambiers", "ischios", "hamstring", "hamstrings"),
}
NONE_WORDS = {"aucune", "aucun", "none", "no", "non", "nope", "rien", "ras", "nothing", "nil", "n/a", "na", "neant", "sans", "no injury", "no injuries", "pas de blessure", "pas de blessures"}
NEGATION = re.compile(r"^(pas de|pas d'|aucune?|sans|no |none|not |nothing|rien|ne\b)")
MAX_TEXT = 300  # un texte plus long est tronqué avant l'analyse

_PATTERNS = {zone: re.compile(r"(?<![a-z])(?:" + "|".join(re.escape(w) for w in sorted(words, key=len, reverse=True)) + r")(?:s|x)?(?![a-z])") for zone, words in ZONE_WORDS.items()}


def fold(text: str) -> str:
    """Minuscules sans accents, apostrophes typographiques ramenées à « ' », espaces normalisés."""
    t = unicodedata.normalize("NFKD", text[:MAX_TEXT].replace("’", "'").replace("‘", "'")).encode("ascii", "ignore").decode().lower()
    return re.sub(r"\s+", " ", t).strip()


def zones_in_text(text: str) -> set[str]:
    """Zones du corps citées dans un texte (français ou anglais, accents, pluriels)."""
    t = fold(text)
    return {zone for zone, pat in _PATTERNS.items() if pat.search(t)}


def _texts(value: Any) -> list[str]:
    """Textes d'une valeur de fait (liste, chaîne ou autre) ; ce qui n'est pas du texte est ignoré."""
    if isinstance(value, str):
        return [value]
    if isinstance(value, list | tuple | set):
        return [v for v in value if isinstance(v, str)]
    return []


def normalize_injuries(facts: dict[str, Any]) -> tuple[set[str], list[str]]:
    """(zones reconnues, textes non reconnus) d'après le menu `history.injuries`, la précision « autre » et le détail libre.

    « aucune », « none », « pas de blessure »… ne donnent rien. Un texte qui ne cite aucune zone connue est conservé tel quel (S7) :
    la blessure n'est pas oubliée en silence, le plan le signale.
    """
    zones: set[str] = set()
    unknown: list[str] = []
    items = [t for k in ("history.injuries", "history.injuries.other", "history.injury_detail") for t in _texts(facts.get(k))]
    for raw in items:
        t = fold(raw)
        if not t or t in NONE_WORDS or t in ("autre", "other") or NEGATION.match(t):
            continue
        found = zones_in_text(t)
        if found:
            zones |= found
        else:
            clean = raw.strip()[:60]
            if clean and clean not in unknown:
                unknown.append(clean)
    return zones, unknown
