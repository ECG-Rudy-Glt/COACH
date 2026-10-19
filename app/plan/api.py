"""API du plan : génération, lecture, réalisation d'une séance."""
from datetime import date, timedelta
from typing import Any, Literal

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, Field

from app.plan.cycles import continue_anchor, describe
from app.plan.engine import advice, build_profile, outlook, plan_weeks
from app.plan.pain import pain_zones
from app.plan.strength import annotate_history, resolve
from app.questionnaire.models import current_facts
from app.repo import Repo


class Generate(BaseModel):
    weeks: int = Field(default=1, ge=1, le=8)  # une semaine à la fois : le coach a lu les retours avant la suivante
    restart_cycle: bool = False  # démarrer un nouveau cycle (sinon le cycle en cours continue)


ALLOWED_LOG = {"rpe", "minutes", "note", "adaptation", "changes", "exercises", "source", "garmin_id", "distance_km", "avg_hr", "max_hr", "calories", "training_load", "garmin_name"}  # noqa: E501
CHANGES = {"plus léger", "plus court", "plus long", "exercice remplacé", "séries en moins", "séries en plus", "douleur", "trop facile", "trop dur", "matériel manquant"}


def clean_log(raw: dict[str, Any] | None) -> dict[str, Any] | None:
    """Limite et nettoie le retour de séance : l'utilisateur raconte ce qu'il a adapté, le coach s'en sert."""
    if raw is None:
        return None
    if len(str(raw)) > 20000:
        raise HTTPException(422, "Retour de séance trop volumineux.")
    out = {k: v for k, v in raw.items() if k in ALLOWED_LOG}
    for k in ("note", "adaptation"):
        if isinstance(out.get(k), str):
            out[k] = out[k].strip()[:600]
    if "changes" in out:
        out["changes"] = [c for c in (out["changes"] if isinstance(out["changes"], list) else []) if c in CHANGES][:8]
    return out


class Done(BaseModel):
    status: Literal["planned", "done", "skipped"]
    logged: dict[str, Any] | None = None


def week_activities(repo: Repo, user_id: int, start: date, sessions: list[dict[str, Any]]) -> list[dict[str, Any]]:
    """Activités Garmin de la semaine qui ne correspondent à aucune séance planifiée (historique réel)."""
    used = {(r["logged"] or {}).get("garmin_id") for r in sessions}
    acts = [a for a in repo.list_activities(user_id, start, 500) if a["day"] < start + timedelta(days=7) and a["garmin_id"] not in used]
    return [{"day": a["day"].isoformat(), "sport": a["sport"], "name": a["name"], "duration_s": a["duration_s"], "distance_m": a["distance_m"]}
            for a in sorted(acts, key=lambda a: a["started_at"])]


def bounds_of(repo: Repo, user_id: int, today: date) -> dict[str, str]:
    """Première et dernière semaine consultables : séances planifiées et activités Garmin confondues."""
    days = [r["day"] for r in repo.list_sessions(user_id, today - timedelta(days=730), None)]
    days += [a["day"] for a in repo.list_activities(user_id, today - timedelta(days=730), 5000)]
    return {"first": min(days, default=today).isoformat(), "last": max([*days, today]).isoformat()}


def serialize(s: dict[str, Any]) -> dict[str, Any]:
    return {**s, "day": s["day"].isoformat(), "created_at": None, "updated_at": None, "user_id": None}


def build_router(get_repo: Any, require_user: Any) -> APIRouter:
    router = APIRouter(prefix="/users/{user_id}/plan", tags=["plan"])

    @router.post("/generate")
    def generate(body: Generate | None = None, user_id: int = Depends(require_user),
                 repo: Repo = Depends(get_repo)) -> dict[str, Any]:
        today = date.today()
        facts = {k: v for k, v in current_facts(repo.list_facts(user_id)).items() if v is not None}
        zones = pain_zones(repo.list_sessions(user_id, today - timedelta(days=21), today), today)
        if zones:  # douleur signalée dans un retour de séance : traitée comme une blessure active (S2) pour cette génération
            facts = {**facts, "history.injuries": sorted({*(facts.get("history.injuries") or []), *zones} - {"aucune"})}
        profile = build_profile(facts, repo.list_goals(user_id, None), today)
        existing = repo.list_sessions(user_id, today - timedelta(days=today.weekday()), None)
        # la semaine en cours n'est jamais bouleversée : on ne remplace qu'à partir de lundi prochain
        cutoff = today + timedelta(days=7 - today.weekday()) if (existing or today.weekday() >= 5) else today  # le week-end, on prépare la semaine suivante
        monday0 = cutoff - timedelta(days=cutoff.weekday())
        recent = repo.list_sessions(user_id, monday0 - timedelta(days=84), monday0)
        anchor = None if (body and body.restart_cycle) else continue_anchor(recent, profile.deload_cycle, monday0)
        sessions = plan_weeks(profile, today, (body.weeks if body else 1), start=cutoff, anchor=anchor)
        repo.delete_planned_from(user_id, cutoff)
        rows = []
        for s in sessions:
            details = dict(s.details)
            if "slots" in details:
                details["slots"] = resolve(repo, details["slots"], facts)
            rows.append({"day": s.date, "kind": s.kind, "title": s.title, "duration_min": s.duration_min,
                         "details": details, "rules": s.rules, "notes": s.notes})
        repo.add_sessions(user_id, rows)
        reason = None
        if not rows:
            reason = ("Un signal d'alerte à l'effort doit d'abord être discuté avec un médecin." if profile.red_flags
                      else "Choisissez au moins la course ou la musculation dans vos sports pour obtenir un plan.")
        return {"created": len(rows), "from": cutoff.isoformat(), "reason": reason}

    @router.get("")
    def get_plan(weeks: int = 4, week: date | None = None, user_id: int = Depends(require_user), repo: Repo = Depends(get_repo)) -> dict[str, Any]:
        today = date.today()
        start = today - timedelta(days=today.weekday())
        if week:  # une semaine précise (navigation dans l'historique)
            start = week - timedelta(days=week.weekday())
            rows = repo.list_sessions(user_id, start, start + timedelta(days=7))
            return {"today": today.isoformat(), "sessions": [serialize(r) for r in annotate_history(rows, repo.list_sessions(user_id, start - timedelta(days=180), None))],
                    "activities": week_activities(repo, user_id, start, rows), "bounds": bounds_of(repo, user_id, today)}
        rows = repo.list_sessions(user_id, start, start + timedelta(days=7 * max(1, min(weeks, 8))))
        rows = annotate_history(rows, repo.list_sessions(user_id, today - timedelta(days=180), None))
        facts = {k: v for k, v in current_facts(repo.list_facts(user_id)).items() if v is not None}
        prof = build_profile(facts, repo.list_goals(user_id, None), today)
        return {"today": today.isoformat(), "sessions": [serialize(r) for r in rows], "bounds": bounds_of(repo, user_id, today), "outlook": outlook(prof, today), "advice": advice(prof),
                "cycle": describe(rows, today)}

    @router.patch("/sessions/{session_id}")
    def update(session_id: int, body: Done, user_id: int = Depends(require_user), repo: Repo = Depends(get_repo)) -> dict[str, Any]:
        row = repo.update_session(user_id, session_id, body.status, clean_log(body.logged))
        if not row:
            raise HTTPException(404, "Séance inconnue.")
        return serialize(row)

    return router
