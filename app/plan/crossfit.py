"""Séance hebdomadaire de conditionnement type CrossFit (règle M9) : échauffement, force/technique, WOD, retour au calme.

Déterministe : le format change chaque semaine du bloc (AMRAP, tours chronométrés, EMOM, allégée), la durée du WOD monte
d'un bloc à l'autre (surcharge, M8) et la semaine allégée reste modérée. Les mouvements incompatibles avec une blessure
déclarée sont remplacés par leur variante.
"""
from __future__ import annotations

from typing import Any

from app.plan.cycles import Cycle

# nom, étiquettes de risque, variante sans risque
MOVES: dict[str, tuple[str, frozenset[str], str]] = {
    "swing": ("Swing kettlebell", frozenset({"hinge"}), "Rameur"),
    "goblet": ("Goblet squat", frozenset({"knee"}), "Rameur"),
    "thruster": ("Thruster haltères", frozenset({"overhead", "knee"}), "Goblet squat léger"),
    "pushup": ("Pompes", frozenset(), "Pompes sur banc"),
    "pullup": ("Tractions", frozenset(), "Rowing inversé"),
    "burpee": ("Burpees", frozenset({"jump"}), "Sprawl sans saut"),
    "stepup": ("Montées de banc", frozenset({"knee"}), "Rameur"),
    "row": ("Rameur (calories)", frozenset(), "Rameur (calories)"),
    "rope": ("Corde à sauter", frozenset({"jump"}), "Rameur (calories)"),
    "situp": ("Relevés de buste", frozenset(), "Planche 30 s"),
    "press": ("Développé épaules haltères", frozenset({"overhead"}), "Pompes déclive"),
    "wallball": ("Wall balls", frozenset({"overhead", "knee"}), "Goblet squat"),
    "carry": ("Marche chargée (farmer)", frozenset(), "Marche chargée (farmer)"),
    "run": ("Course 200 m", frozenset(), "Rameur (calories)"),
}
AVOID = {"genou": {"knee", "jump"}, "épaule": {"overhead"}, "dos": {"hinge"}, "cheville": {"jump"}, "tendon d'Achille": {"jump"}, "hanche": {"knee"}}
SCALE = {"débutant": 0.7, "intermédiaire": 1.0, "avancé": 1.2, "expert": 1.2}

# circuits : (mouvement, répétitions de base)
CIRCUITS = [
    [("swing", 15), ("pushup", 10), ("goblet", 12)],
    [("row", 12), ("thruster", 10), ("pullup", 6), ("situp", 15)],
    [("burpee", 8), ("wallball", 12), ("carry", 30), ("press", 10)],
]
STRENGTH_PAIRS = [("goblet", "pullup"), ("swing", "pushup"), ("press", "carry")]


def _avoid(injuries: set[str]) -> set[str]:
    out: set[str] = set()
    for i in injuries:
        out |= AVOID.get(i, set())
    return out


def _move(key: str, reps: int, scale: float, bad: set[str]) -> str:
    name, tags, alt = MOVES[key]
    n = round(reps * scale)
    if tags & bad:
        return f"{n} cal de rameur" if alt.startswith("Rameur") else alt if alt.startswith("Planche") else f"{n} {alt.lower()}"
    if key == "carry":
        return f"{round(reps * scale)} m {name.lower()}"
    if key == "row":
        return f"{round(reps * scale)} cal {name.removesuffix(' (calories)').lower()}"
    return f"{round(reps * scale)} {name.lower()}"


def build(cyc: Cycle, level: str, injuries: set[str], variant_offset: int = 0) -> tuple[int, dict[str, Any], list[str]]:
    """(durée en minutes, détails, notes) de la séance de la semaine."""
    scale = SCALE.get(level, 1.0)
    bad = _avoid(injuries)
    wib = cyc.week_in_block - 1
    circuit = CIRCUITS[(cyc.block_no - 1 + wib + variant_offset) % len(CIRCUITS)]
    items = [_move(k, r, scale, bad) for k, r in circuit]
    pair = STRENGTH_PAIRS[(cyc.block_no - 1 + wib + variant_offset) % len(STRENGTH_PAIRS)]
    strength = [_move(pair[0], 8, scale, bad), _move(pair[1], 6, scale, bad)]
    long_wod = min(12 + 2 * (cyc.block_no - 1), 18)
    if cyc.deload:
        fmt, wod_min, effort = f"AMRAP {8} min, allure confortable", 8, "6 sur 10 : vous pourriez parler entre les tours"
        wod_text = [f"AMRAP 8 min : {' + '.join(items)}"]
    elif wib == 0:
        fmt, wod_min, effort = f"AMRAP {long_wod} min", long_wod, "7 sur 10, allure tenable sur toute la durée"
        wod_text = [f"AMRAP {long_wod} min — tours de : " + ", ".join(items)]
    elif wib == 1:
        rounds = 4 + min(cyc.block_no - 1, 2)
        fmt, wod_min, effort = f"{rounds} tours chronométrés", 6 + rounds * 3, "8 sur 10 sur les derniers tours, jamais d'échec technique"
        wod_text = [f"{rounds} tours, le plus vite possible avec une bonne exécution : " + ", ".join(items)]
    else:
        emom = min(12 + 2 * (cyc.block_no - 1), 18)
        fmt, wod_min, effort = f"EMOM {emom} min", emom, "7 à 8 sur 10, 10 à 15 s de repos par minute"
        stations = ", ".join(f"minute {i + 1} : {it}" for i, it in enumerate(items))
        wod_text = [f"EMOM {emom} min, en boucle — {stations}"]
    blocks = [
        {"title": "Échauffement", "minutes": 8, "items": ["3 min de rameur ou vélo facile", "Mobilité épaules, hanches et chevilles", "2 tours : 8 squats, 6 pompes, 10 balancements de jambe"]},
        {"title": "Force et technique", "minutes": 12, "items": [f"3 séries de : {strength[0]} puis {strength[1]}, repos 90 s", "Charge pour finir avec 2 à 3 répétitions en réserve"]},
        {"title": f"WOD — {fmt}", "minutes": wod_min, "items": wod_text, "effort": effort},
        {"title": "Retour au calme", "minutes": 5, "items": ["Marche, respiration, étirements doux des hanches et épaules"]},
    ]
    notes = ["Séance de conditionnement : intensité plus haute que la musculation, à garder loin de la sortie longue.",
             "Adaptez la charge ou prenez la variante plutôt que de sacrifier la technique ; notez votre score (tours ou temps) dans la remarque."]
    if cyc.deload:
        notes.append("Semaine allégée : on garde le mouvement, pas la fatigue.")
    if bad:
        notes.append("Certains mouvements sont remplacés par une variante à cause de vos blessures déclarées.")
    return 8 + 12 + wod_min + 5, {"variant": "crossfit", "blocks": blocks}, notes
