"""Muscles travaillés : correspondance bibliothèque -> groupes du schéma, et calcul pondéré par séries (règles ST21 à ST24).

Les noms de muscles de la bibliothèque (`app/exercises/labels.py: MUSCLE_FR`) sont regroupés en quinze groupes dessinés dans le schéma. Cette table est l'unique
endroit de la correspondance : un test échoue si un muscle de la bibliothèque n'y figure pas.
"""
from collections import defaultdict
from datetime import date, timedelta
from typing import Any

from app.exercises.sources import norm_key
from app.stats.progress import valid_sets

SECONDARY_WEIGHT = 0.5  # convention de comptage (ST22), pas une constante physiologique
MIN_SETS_FOR_FLAGS = 8  # en dessous, aucun déséquilibre n'est signalé : trop peu de séries pour comparer (ST24)
PUSH_PULL_BAND = (2 / 3, 3 / 2)  # rapport poussée / tirage toléré
LEGS_MIN_SHARE = 0.2  # part minimale des séries pondérées sur les jambes
CORE_MIN_SHARE = 0.08  # part minimale sur le tronc

# groupe -> (libellé français, famille). Familles : push, pull, legs, core, other.
GROUPS: dict[str, tuple[str, str]] = {
    "chest": ("Pectoraux", "push"), "shoulders": ("Épaules", "push"), "triceps": ("Triceps", "push"),
    "lats": ("Grand dorsal", "pull"), "middle_back": ("Milieu du dos", "pull"), "traps": ("Trapèzes et nuque", "pull"), "biceps": ("Biceps", "pull"),
    "forearms": ("Avant-bras", "other"),
    "abs": ("Abdominaux", "core"), "lower_back": ("Bas du dos", "core"),
    "glutes": ("Fessiers", "legs"), "quadriceps": ("Quadriceps", "legs"), "hamstrings": ("Ischio-jambiers", "legs"), "adductors": ("Adducteurs", "legs"), "calves": ("Mollets", "legs"),
}

# nom de muscle de la bibliothèque -> groupe du schéma
MUSCLE_TO_GROUP: dict[str, str] = {
    "abdominals": "abs", "abductors": "glutes", "adductors": "adductors", "biceps": "biceps", "calves": "calves", "chest": "chest", "forearms": "forearms",
    "glutes": "glutes", "hamstrings": "hamstrings", "lats": "lats", "lower back": "lower_back", "middle back": "middle_back", "neck": "traps",
    "quadriceps": "quadriceps", "shoulders": "shoulders", "traps": "traps", "triceps": "triceps",
}

FAMILY_FR = {"push": "Poussée", "pull": "Tirage", "legs": "Jambes", "core": "Tronc"}
KIND_PREFIX = "strength_"


def is_strength(kind: str) -> bool:
    return kind.startswith(KIND_PREFIX) and kind != "strength_crossfit"


def muscles_of(primary: list[str], secondary: list[str]) -> tuple[set[str], set[str]]:
    """Groupes principaux et secondaires d'un exercice ; un groupe principal n'est jamais compté aussi comme secondaire."""
    p = {MUSCLE_TO_GROUP[m] for m in primary if m in MUSCLE_TO_GROUP}
    s = {MUSCLE_TO_GROUP[m] for m in secondary if m in MUSCLE_TO_GROUP} - p
    return p, s


class Resolver:
    """Retrouve les muscles d'un exercice saisi par son nom (bibliothèque, sinon muscle principal du mouvement du moteur). Un nom inconnu reste inconnu : rien n'est deviné."""

    def __init__(self, repo: Any, patterns: dict[str, tuple[str, str]]) -> None:
        self.repo, self.patterns, self.cache = repo, patterns, {}

    def __call__(self, name: str) -> tuple[set[str], set[str]] | None:
        if name in self.cache:
            return self.cache[name]
        found = None
        key = norm_key(name)
        rows, _ = self.repo.search_exercises(name[:60], None, None, None, 100, 0)
        for e in rows:
            if key in (norm_key(e.name), norm_key(e.name_en or "")):
                found = muscles_of(e.muscles_primary, e.muscles_secondary)
                break
        if found is None and name in self.patterns:
            found = muscles_of([self.patterns[name][0]], [])
        if found is not None and not (found[0] or found[1]):
            found = None
        self.cache[name] = found
        return found


def session_volume(logged: dict[str, Any] | None, resolve: Resolver) -> tuple[dict[str, float], dict[str, float], int, list[str]]:
    """(séries pondérées, séries principales, séries comptées, exercices sans muscle connu) d'une séance faite."""
    weighted: dict[str, float] = defaultdict(float)
    primary: dict[str, float] = defaultdict(float)
    counted, unknown = 0, []
    for ex in (logged or {}).get("exercises") or []:
        if not isinstance(ex, dict) or not isinstance(ex.get("name"), str):
            continue
        n = len(valid_sets(ex))
        if not n:
            continue
        m = resolve(ex["name"][:80])
        if m is None:
            unknown.append(ex["name"][:80])
            continue
        counted += n
        for g in m[0]:
            weighted[g] += n
            primary[g] += n
        for g in m[1]:
            weighted[g] += n * SECONDARY_WEIGHT
    return dict(weighted), dict(primary), counted, unknown


def table(weighted: dict[str, float], primary: dict[str, float]) -> list[dict[str, Any]]:
    """Une ligne par groupe, y compris ceux à zéro : le tableau est l'alternative texte du schéma."""
    top = max(weighted.values(), default=0)
    rows = [{"group": g, "label": label, "family": fam, "sets": round(weighted.get(g, 0), 1), "primary_sets": round(primary.get(g, 0), 1),
             "level": 0 if not weighted.get(g) else (2 if primary.get(g) else 1), "share": round(weighted.get(g, 0) / top, 2) if top else 0}
            for g, (label, fam) in GROUPS.items()]
    return sorted(rows, key=lambda r: (-r["sets"], r["label"]))


def balance(weighted: dict[str, float]) -> dict[str, Any]:
    """Séries pondérées par famille et alertes douces (ST24) : jamais un verdict, seulement un repérage."""
    fam: dict[str, float] = {f: 0.0 for f in FAMILY_FR}
    for g, v in weighted.items():
        f = GROUPS[g][1]
        if f in fam:
            fam[f] += v
    total = sum(fam.values())
    flags: list[str] = []
    if total >= MIN_SETS_FOR_FLAGS:
        if fam["push"] and fam["pull"]:
            ratio = fam["push"] / fam["pull"]
            if ratio > PUSH_PULL_BAND[1]:
                flags.append("push_heavy")
            elif ratio < PUSH_PULL_BAND[0]:
                flags.append("pull_heavy")
        elif fam["push"] or fam["pull"]:
            flags.append("push_heavy" if fam["push"] else "pull_heavy")
        if fam["legs"] / total < LEGS_MIN_SHARE:
            flags.append("legs_low")
        if fam["core"] / total < CORE_MIN_SHARE:
            flags.append("core_low")
    return {"families": {f: round(v, 1) for f, v in fam.items()}, "total": round(total, 1), "flags": flags,
            "ratio": round(fam["push"] / fam["pull"], 2) if fam["pull"] else None}


def monday(d: date) -> date:
    return d - timedelta(days=d.weekday())


def view(weighted: dict[str, float], primary: dict[str, float], counted: int, unknown: list[str]) -> dict[str, Any]:
    return {"supported": True, "rows": table(weighted, primary), "balance": balance(weighted), "sets_counted": counted, "unknown": sorted(set(unknown))[:20],
            "weights": {"primary": 1.0, "secondary": SECONDARY_WEIGHT}}
