"""Période d'absence (G20) : voyage, maladie, blessure, pas de matériel. Déterministe, sans LLM.

Les séances prévues pendant la période sont passées (jamais rattrapées, G18) ; la première semaine après la période est allégée selon la raison
(reprise progressive, dans l'esprit de G3). Rien n'est ajouté : la charge ne peut que baisser.
"""
from datetime import date, timedelta
from typing import Any

REASONS = {"voyage": 0.85, "maladie": 0.7, "blessure": 0.7, "matériel": 1.0}  # facteur de la semaine de reprise ; 1,0 = pas d'allègement (convention de pratique)
RETURN_DAYS = 7
MAX_DAYS = 90
MIN_SESSION = 15
HEALTH_NOTE = "Reprenez en douceur ; si une douleur ou un symptôme persiste, consultez un professionnel de santé (S1)."


def effects(rows: list[dict[str, Any]], start: date, end: date, reason: str, today: date) -> list[dict[str, Any]]:
    """Changements à appliquer aux séances encore prévues : `skip` pendant la période, `reduce` la semaine de reprise."""
    factor = REASONS[reason]
    out: list[dict[str, Any]] = []
    for r in rows:
        if r["status"] != "planned" or r["day"] < today:
            continue
        if start <= r["day"] <= end:
            out.append({"session_id": r["id"], "action": "skip", "title": r["title"], "day": r["day"].isoformat()})
        elif end < r["day"] <= end + timedelta(days=RETURN_DAYS) and factor < 1:
            out.append({"session_id": r["id"], "action": "reduce", "title": r["title"], "day": r["day"].isoformat(), "duration_to": max(MIN_SESSION, round(r["duration_min"] * factor))})
    return out


def validate(start: date, end: date, reason: str, today: date) -> str | None:
    if reason not in REASONS:
        return "Raison inconnue."
    if end < start:
        return "La fin de la période précède son début."
    if (end - start).days + 1 > MAX_DAYS:
        return f"Période trop longue ({MAX_DAYS} jours au plus) : au-delà, refaites le questionnaire."
    if end < today:
        return "La période est déjà passée."
    return None
