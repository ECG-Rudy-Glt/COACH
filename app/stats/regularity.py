"""Régularité : semaines tenues, série en cours, objectif de la semaine (règles ST11 à ST13).

Pensé sans pression : une séance passée volontairement n'est pas un échec, une semaine sans séance prévue garde la série intacte, la semaine en cours ne
peut jamais « casser » une série, et rien ici ne déclenche de notification. Pas de badges.
"""
from __future__ import annotations

import math
from datetime import date, timedelta
from typing import Any

WEEK_SHARE = 0.75  # une semaine est « tenue » quand au moins 75 % des séances prévues sont faites (repère de pratique, ST11)
SHOWN_WEEKS = 12
HISTORY_WEEKS = 52


def monday_of(d: date) -> date:
    return d - timedelta(days=d.weekday())


def week_rows(sessions: list[dict[str, Any]], today: date, weeks: int = HISTORY_WEEKS) -> list[dict[str, Any]]:
    """Une ligne par semaine (lundi au dimanche), de la plus ancienne à la semaine en cours.

    `met` : True (tenue), False (non tenue) ou None (rien à juger : aucune séance prévue, ou semaine en cours pas encore tenue). Une séance passée
    volontairement (« skipped ») sort du calcul ; une séance passée sans retour compte comme non faite. Une séance ajoutée à la main hors plan n'est
    pas une séance prévue par le moteur : elle n'entre pas dans le calcul (sinon une séance en plus rattraperait une séance manquée).
    """
    this = monday_of(today)
    out = []
    for i in range(weeks):
        mon = this - timedelta(weeks=weeks - 1 - i)
        week = [s for s in sessions if mon <= s["day"] < mon + timedelta(days=7) and not (s.get("details") or {}).get("manual")]
        done = sum(1 for s in week if s["status"] == "done")
        skipped = sum(1 for s in week if s["status"] == "skipped")
        planned = len(week) - skipped
        current = mon == this
        reached = planned > 0 and done / planned >= WEEK_SHARE
        met = (True if reached else None) if current else (reached if planned > 0 else None)
        out.append({"monday": mon.isoformat(), "planned": planned, "done": done, "skipped": skipped, "met": met, "current": current})
    return out


def streaks(rows: list[dict[str, Any]]) -> dict[str, int]:
    """Série en cours (en semaines tenues) et meilleure série. Une semaine sans rien à juger ne casse ni ne prolonge la série (ST12)."""
    best = run = 0
    for r in rows:
        if r["met"] is True:
            run += 1
            best = max(best, run)
        elif r["met"] is False:
            run = 0
    # série en cours : à partir de la dernière semaine jugée
    cur = 0
    for r in reversed(rows):
        if r["met"] is True:
            cur += 1
        elif r["met"] is False:
            break
    return {"current": cur, "best": best}


def goal_block(row: dict[str, Any], today: date) -> dict[str, Any]:
    """Objectif de la semaine en cours : les séances prévues par le moteur ; rien n'est ajouté par l'écran."""
    planned, done = row["planned"], row["done"]
    return {"planned": planned, "done": done, "skipped": row["skipped"], "needed": math.ceil(planned * WEEK_SHARE) if planned else 0, "met": row["met"] is True,
            "days_left": 6 - today.weekday()}


def regularity_view(sessions: list[dict[str, Any]], today: date) -> dict[str, Any]:
    rows = week_rows(sessions, today)
    shown = rows[-SHOWN_WEEKS:]
    judged = [r for r in shown if not r["current"] and r["met"] is not None]
    return {"enabled": True, "today": today.isoformat(), "goal": goal_block(rows[-1], today), "streak": streaks(rows), "weeks": shown,
            "summary": {"weeks_met": sum(1 for r in judged if r["met"]), "weeks_judged": len(judged), "sessions_done": sum(r["done"] for r in shown),
                        "sessions_planned": sum(r["planned"] for r in shown), "share": WEEK_SHARE}}
