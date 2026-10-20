from typing import Any

from app.questionnaire.conditions import evaluate
from app.questionnaire.models import Fact, Question, current_facts

# Ordre des domaines : plus petit = posé en premier.
DOMAIN_PRIORITY = {
    "goals": 0,
    "health": 1,
    "constraints": 2,
    "history": 3,
    "multisport": 4,
    "running": 5,
    "trail": 6,
    "strength": 7,
    "hybrid": 8,
    "cycling": 9,
    "mobility": 10,
    "project": 11,
}


def pending(bank: list[Question], facts: list[Fact]) -> list[Question]:
    """Questions visibles (conditions satisfaites) et sans réponse, dans l'ordre de pose."""
    cur: dict[str, Any] = current_facts(facts)
    todo = [q for q in bank if q.fact_key not in cur and evaluate(q.show_if, cur)]
    return sorted(todo, key=lambda q: (DOMAIN_PRIORITY.get(q.domain, 99), q.order, q.id))


def next_questions(
    bank: list[Question], facts: list[Fact], n: int = 1, domain: str | None = None, essential: bool = False
) -> list[Question]:
    todo = pending(bank, facts)
    if domain:
        todo = [q for q in todo if q.domain == domain]
    if essential:
        todo = [q for q in todo if q.essential]
    return todo[:n]


def progress(bank: list[Question], facts: list[Fact]) -> dict[str, Any]:
    cur = current_facts(facts)
    todo = pending(bank, facts)
    domains: dict[str, dict[str, int]] = {}
    for q in bank:
        if q.fact_key in cur:
            domains.setdefault(q.domain, {"answered": 0, "remaining": 0})["answered"] += 1
    for q in todo:
        domains.setdefault(q.domain, {"answered": 0, "remaining": 0})["remaining"] += 1
    ordered = dict(sorted(domains.items(), key=lambda kv: DOMAIN_PRIORITY.get(kv[0], 99)))
    ess_done = sum(1 for q in bank if q.essential and q.fact_key in cur)
    ess_left = sum(1 for q in todo if q.essential)
    return {
        "answered": sum(d["answered"] for d in ordered.values()),
        "remaining_visible": len(todo),
        "domains": ordered,
        "essential": {"answered": ess_done, "remaining": ess_left},
    }
