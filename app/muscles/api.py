"""Muscles travaillés : une séance de force faite, ou une semaine (règles ST21 à ST24). Tout est calculé ici, jamais par un LLM."""
from datetime import date, timedelta
from typing import Any

from fastapi import APIRouter, Depends, HTTPException, Query

from app.muscles import groups as G
from app.plan.api import find_session
from app.plan.strength import PATTERNS
from app.repo import Repo


def week_view(repo: Repo, user_id: int, day: date) -> dict[str, Any]:
    start = G.monday(day)
    end = start + timedelta(days=6)
    resolve = G.Resolver(repo, PATTERNS)
    weighted: dict[str, float] = {}
    primary: dict[str, float] = {}
    counted, unknown, sessions = 0, [], 0
    for s in repo.list_sessions(user_id, start, end):
        if s["status"] != "done" or not G.is_strength(s["kind"]):
            continue
        w, p, n, u = G.session_volume(s.get("logged"), resolve)
        if n or u:
            sessions += 1
        counted += n
        unknown += u
        for g, v in w.items():
            weighted[g] = weighted.get(g, 0) + v
        for g, v in p.items():
            primary[g] = primary.get(g, 0) + v
    return {**G.view(weighted, primary, counted, unknown), "week_start": start.isoformat(), "week_end": end.isoformat(), "sessions": sessions, "current": start == G.monday(date.today())}


def build_router(get_repo: Any, require_user: Any) -> APIRouter:
    router = APIRouter(prefix="/users/{user_id}", tags=["muscles"])

    @router.get("/plan/sessions/{session_id}/muscles")
    def session_muscles(session_id: int, user_id: int = Depends(require_user), repo: Repo = Depends(get_repo)) -> dict[str, Any]:
        row = find_session(repo, user_id, session_id, date.today())
        if row["status"] != "done":
            return {"supported": False, "reason": "not_done"}
        if not G.is_strength(row["kind"]):
            return {"supported": False, "reason": "no_diagram"}  # course, vélo, natation, marche : aucun schéma modélisé (ST21)
        return G.view(*G.session_volume(row.get("logged"), G.Resolver(repo, PATTERNS)))

    @router.get("/stats/muscles")
    def week_muscles(week: date | None = Query(None), user_id: int = Depends(require_user), repo: Repo = Depends(get_repo)) -> dict[str, Any]:
        day = week or date.today()
        if abs((date.today() - day).days) > 730:
            raise HTTPException(422, "Semaine hors de la période suivie.")
        return week_view(repo, user_id, day)

    return router
