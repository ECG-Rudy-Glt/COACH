"""Évaluation des conditions `show_if` sur les faits courants.

Grammaire : {all: [..]} | {any: [..]} | {not: cond} | {fact: clé, <op>: valeur}
Opérateurs : eq, in, contains, gte, lte, exists, len_gte (longueur d'une liste).
Un fait absent rend la feuille fausse (sauf `exists: false`).
"""
from typing import Any

OPS = ("eq", "in", "contains", "gte", "lte", "exists", "len_gte")


def fact_refs(cond: dict[str, Any] | None) -> set[str]:
    """Clés de faits référencées par une condition."""
    if not cond:
        return set()
    if "all" in cond:
        return set().union(*(fact_refs(c) for c in cond["all"])) if cond["all"] else set()
    if "any" in cond:
        return set().union(*(fact_refs(c) for c in cond["any"])) if cond["any"] else set()
    if "not" in cond:
        return fact_refs(cond["not"])
    return {cond["fact"]}


def validate_condition(cond: dict[str, Any]) -> None:
    if "all" in cond or "any" in cond:
        key = "all" if "all" in cond else "any"
        if not isinstance(cond[key], list) or not cond[key]:
            raise ValueError(f"'{key}' doit être une liste non vide")
        for c in cond[key]:
            validate_condition(c)
        return
    if "not" in cond:
        validate_condition(cond["not"])
        return
    if "fact" not in cond:
        raise ValueError(f"condition sans 'fact' : {cond}")
    ops = [k for k in cond if k in OPS]
    if len(ops) != 1 or len(cond) != 2:
        raise ValueError(f"une feuille a exactement un opérateur parmi {OPS} : {cond}")


def evaluate(cond: dict[str, Any] | None, facts: dict[str, Any]) -> bool:
    if not cond:
        return True
    if "all" in cond:
        return all(evaluate(c, facts) for c in cond["all"])
    if "any" in cond:
        return any(evaluate(c, facts) for c in cond["any"])
    if "not" in cond:
        return not evaluate(cond["not"], facts)

    key = cond["fact"]
    present = facts.get(key) is not None  # None = question passée
    if "exists" in cond:
        return present == bool(cond["exists"])
    if not present:
        return False
    value = facts[key]
    if "eq" in cond:  # sur une liste (réponse multiple), eq = « contient »
        return cond["eq"] in value if isinstance(value, list) else value == cond["eq"]
    if "in" in cond:  # sur une liste, au moins un élément dans l'ensemble
        if isinstance(value, list):
            return any(v in cond["in"] for v in value)
        return value in cond["in"]
    if "contains" in cond:
        return isinstance(value, list | str) and cond["contains"] in value
    if "len_gte" in cond:
        return isinstance(value, list) and len(value) >= cond["len_gte"]
    if "gte" in cond:
        return isinstance(value, int | float) and value >= cond["gte"]
    return isinstance(value, int | float) and value <= cond["lte"]
