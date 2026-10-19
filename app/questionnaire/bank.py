"""Chargement et validation de la banque de questions (YAML)."""
from pathlib import Path

import yaml

from app.questionnaire.conditions import fact_refs, validate_condition
from app.questionnaire.models import Question

# Faits fournis par d'autres sources que le questionnaire (Garmin, saisie, dérivés).
EXTERNAL_FACTS: set[str] = set()


def load_bank(directory: Path) -> list[Question]:
    questions: list[Question] = []
    for path in sorted(directory.glob("*.yaml")):
        if path.name.endswith(".example.yaml") or path.name == "benchmarks.yaml":
            continue
        for raw in yaml.safe_load(path.read_text(encoding="utf-8")) or []:
            questions.append(Question(**raw))
    return questions


def validate_bank(questions: list[Question], external: set[str] = EXTERNAL_FACTS) -> list[str]:
    """Retourne la liste des problèmes (vide si la banque est saine)."""
    problems: list[str] = []
    ids = [q.id for q in questions]
    problems += [f"id dupliqué : {i}" for i in {i for i in ids if ids.count(i) > 1}]
    keys = [q.fact_key for q in questions]
    problems += [f"fact_key dupliquée : {k}" for k in {k for k in keys if keys.count(k) > 1}]

    produced = set(keys) | external
    by_key = {q.fact_key: q for q in questions}
    deps: dict[str, set[str]] = {}
    for q in questions:
        if q.type in ("single", "multi") and not q.options:
            problems.append(f"{q.id} : options manquantes")
        try:
            if q.show_if:
                validate_condition(q.show_if)
        except ValueError as e:
            problems.append(f"{q.id} : {e}")
            continue
        refs = fact_refs(q.show_if)
        for r in refs - produced:
            problems.append(f"{q.id} : dépend de '{r}' que personne ne produit")
        deps[q.fact_key] = {r for r in refs if r in by_key}

    # Cycles de dépendances : une question qui dépend (indirectement) d'elle-même est inatteignable.
    state: dict[str, int] = {}

    def visit(k: str, path: list[str]) -> None:
        if state.get(k) == 2:
            return
        if state.get(k) == 1:
            problems.append("cycle : " + " -> ".join([*path[path.index(k):], k]))
            return
        state[k] = 1
        for d in deps.get(k, ()):
            visit(d, [*path, k])
        state[k] = 2

    for k in deps:
        visit(k, [])
    return problems
