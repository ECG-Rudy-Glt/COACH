"""API du plan : génération, lecture, réalisation d'une séance."""
from datetime import date, timedelta
from typing import Any, Literal

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, Field

from app.garmin.match import auto_link, link_fields, suggestions, unlink_fields
from app.plan import trajectory
from app.plan.cycles import continue_anchor, describe
from app.plan.engine import KEY, advice, build_profile, empty_reason, outlook, plan_weeks, warnings
from app.plan.level import with_estimates
from app.plan.pain import pain_zones
from app.plan.strength import annotate_history, resolve
from app.questionnaire.models import current_facts
from app.repo import Repo


class Generate(BaseModel):
    weeks: int = Field(default=1, ge=1, le=8)  # une semaine à la fois : le coach a lu les retours avant la suivante
    restart_cycle: bool = False  # démarrer un nouveau cycle (sinon le cycle en cours continue)


MOVE_PAST_DAYS = 56  # on ne rattache pas une séance à plus de 8 semaines en arrière
MOVE_FUTURE_DAYS = 120
ALLOWED_LOG = {"rpe", "minutes", "note", "adaptation", "changes", "exercises", "source", "garmin_id", "distance_km", "avg_hr", "max_hr", "calories", "training_load", "garmin_name"}  # noqa: E501
CHANGES = {"plus léger", "plus court", "plus long", "exercice remplacé", "séries en moins", "séries en plus", "douleur", "trop facile", "trop dur", "matériel manquant"}


def estimated_facts(repo: Repo, user_id: int, facts: dict[str, Any], goals: list[dict[str, Any]], today: date) -> dict[str, Any]:
    """Faits + niveau récent estimé (C14, C15) d'après les sorties de la montre et les charges saisies."""
    acts = repo.list_activities(user_id, today - timedelta(days=56), 500)
    sess = repo.list_sessions(user_id, today - timedelta(days=84), today)
    return with_estimates(facts, acts, sess, goals, today)


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


class Link(BaseModel):
    garmin_id: str = Field(min_length=1, max_length=40)
    move: bool = True  # activité faite un autre jour : la séance suit l'activité


class Move(BaseModel):
    day: date


class Done(BaseModel):
    status: Literal["planned", "done", "skipped"]
    logged: dict[str, Any] | None = None


def week_activities(repo: Repo, user_id: int, start: date, sessions: list[dict[str, Any]]) -> list[dict[str, Any]]:
    """Activités Garmin de la semaine qui ne correspondent à aucune séance planifiée, avec les séances auxquelles on peut les rapprocher."""
    used = {(r["logged"] or {}).get("garmin_id") for r in sessions}
    acts = [a for a in repo.list_activities(user_id, start, 500) if a["day"] < start + timedelta(days=7) and a["garmin_id"] not in used]
    around = repo.list_sessions(user_id, start - timedelta(days=3), start + timedelta(days=10))
    return [{"garmin_id": a["garmin_id"], "day": a["day"].isoformat(), "sport": a["sport"], "name": a["name"], "duration_s": a["duration_s"],
             "distance_m": a["distance_m"], "avg_hr": a["avg_hr"], "suggestions": suggestions(a, around)}
            for a in sorted(acts, key=lambda a: a["started_at"])]


def find_session(repo: Repo, user_id: int, session_id: int, today: date) -> dict[str, Any]:
    row = next((r for r in repo.list_sessions(user_id, today - timedelta(days=MOVE_PAST_DAYS * 2), None) if r["id"] == session_id), None)
    if not row:
        raise HTTPException(404, "Séance inconnue.")
    return row


def move_warnings(moved: dict[str, Any], around: list[dict[str, Any]]) -> list[str]:
    """Avertissements non bloquants après un déplacement : deux séances clés à moins de 48 h (G5), jambes collées à une sortie clé (I1, I2)."""
    out = []
    keys = [r for r in around if r["id"] != moved["id"] and r["status"] != "skipped" and r["kind"] in KEY and abs((r["day"] - moved["day"]).days) < 2]
    if moved["kind"] in KEY and keys:
        out.append("Deux séances exigeantes à moins de 48 h : la récupération sera plus courte (G5).")
    if moved["kind"] == "strength_lower" and any(r["kind"] in ("run_long", "run_quality") for r in keys):
        out.append("Séance de jambes la veille, le jour ou le lendemain d'une séance de course clé : à éviter (I1, I2).")
    if moved["kind"] in ("run_long", "run_quality") and any(r["kind"] == "strength_lower" for r in keys) and not out:
        out.append("Séance de course clé juste à côté d'une séance de jambes : à éviter (I1, I2).")
    return out


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
        goals = repo.list_goals(user_id, None)
        facts = estimated_facts(repo, user_id, facts, goals, today)  # C14/C15 : niveau récent estimé, sans toucher aux saisies
        profile = build_profile(facts, goals, today)
        facts = {**facts, "history.injuries": sorted(profile.injuries)}  # zones normalisées (S2, S7) pour le choix des exercices
        existing = repo.list_sessions(user_id, today - timedelta(days=today.weekday()), None)
        next_monday = today + timedelta(days=7 - today.weekday())
        # la semaine en cours n'est jamais bouleversée : on ne remplace qu'à partir de lundi prochain
        cutoff = next_monday if (existing or today.weekday() >= 5) else today  # le week-end, on prépare la semaine suivante

        def build(start: date) -> list[Any]:
            monday0 = start - timedelta(days=start.weekday())
            recent = repo.list_sessions(user_id, monday0 - timedelta(days=84), monday0)
            anchor = None if (body and body.restart_cycle) else continue_anchor(recent, profile.deload_cycle, monday0)
            return plan_weeks(profile, today, (body.weeks if body else 1), start=start, anchor=anchor)

        sessions = build(cutoff)
        if not sessions and cutoff < next_monday and not (profile.red_flags or profile.no_days):  # G10 : le reste de la semaine est vide (jours passés ou bloqués) : on prépare la suivante
            cutoff = next_monday
            sessions = build(cutoff)
        repo.delete_planned_from(user_id, cutoff)
        rows = []
        for s in sessions:
            details = dict(s.details)
            if "slots" in details:
                details["slots"] = resolve(repo, details["slots"], facts)
            rows.append({"day": s.date, "kind": s.kind, "title": s.title, "duration_min": s.duration_min,
                         "details": details, "rules": s.rules, "notes": s.notes})
        repo.add_sessions(user_id, rows)
        return {"created": len(rows), "from": cutoff.isoformat(), "reason": None if rows else empty_reason(profile), "warnings": warnings(profile)}

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
        goals = repo.list_goals(user_id, None)
        facts = estimated_facts(repo, user_id, facts, goals, today)
        prof = build_profile(facts, goals, today)
        return {"today": today.isoformat(), "sessions": [serialize(r) for r in rows], "bounds": bounds_of(repo, user_id, today), "outlook": outlook(prof, today), "advice": advice(prof),
                "cycle": describe(rows, today), "trajectory": trajectory.describe(prof.target, facts, goals, today)}

    @router.post("/match")
    def match(user_id: int = Depends(require_user), repo: Repo = Depends(get_repo)) -> dict[str, int]:
        """Rapproche les activités Garmin déjà synchronisées des séances (utile quand la séance a été saisie à la main après la synchronisation)."""
        return {"linked": auto_link(repo, user_id, date.today())}

    @router.post("/sessions/{session_id}/link")
    def link(session_id: int, body: Link, user_id: int = Depends(require_user), repo: Repo = Depends(get_repo)) -> dict[str, Any]:
        today = date.today()
        row = find_session(repo, user_id, session_id, today)
        act = next((a for a in repo.list_activities(user_id, today - timedelta(days=MOVE_PAST_DAYS * 2), 5000) if a["garmin_id"] == body.garmin_id), None)
        if not act:
            raise HTTPException(404, "Activité inconnue.")
        window = repo.list_sessions(user_id, act["day"] - timedelta(days=MOVE_PAST_DAYS * 2), None)
        if any((r["logged"] or {}).get("garmin_id") == body.garmin_id and r["id"] != session_id for r in window):
            raise HTTPException(409, "Cette activité est déjà reliée à une autre séance.")
        base = {**row, "logged": unlink_fields(row["logged"])} if (row["logged"] or {}).get("garmin_id") else row  # remplace une ancienne liaison
        updated = repo.update_session(user_id, session_id, "done", link_fields(base, act))
        if body.move and act["day"] != row["day"]:
            updated = repo.move_session(user_id, session_id, act["day"]) or updated
        return serialize(updated)

    @router.delete("/sessions/{session_id}/link")
    def unlink(session_id: int, user_id: int = Depends(require_user), repo: Repo = Depends(get_repo)) -> dict[str, Any]:
        row = find_session(repo, user_id, session_id, date.today())
        if not (row["logged"] or {}).get("garmin_id"):
            raise HTTPException(404, "Aucune activité reliée à cette séance.")
        return serialize(repo.update_session(user_id, session_id, row["status"], unlink_fields(row["logged"])) or row)

    @router.patch("/sessions/{session_id}/move")
    def move(session_id: int, body: Move, user_id: int = Depends(require_user), repo: Repo = Depends(get_repo)) -> dict[str, Any]:
        today = date.today()
        row = find_session(repo, user_id, session_id, today)
        if not today - timedelta(days=MOVE_PAST_DAYS) <= body.day <= today + timedelta(days=MOVE_FUTURE_DAYS):
            raise HTTPException(422, "Date hors de la période possible.")
        if row["status"] == "planned" and body.day < today:
            raise HTTPException(422, "Une séance à venir se reprogramme à aujourd'hui ou plus tard (pour une séance déjà faite, reliez l'activité).")
        if row["status"] == "done" and body.day > today:
            raise HTTPException(422, "Une séance déjà faite ne peut pas être placée dans le futur.")
        moved = repo.move_session(user_id, session_id, body.day)
        if not moved:
            raise HTTPException(404, "Séance inconnue.")
        around = repo.list_sessions(user_id, body.day - timedelta(days=2), body.day + timedelta(days=3))
        return {"session": serialize(moved), "warnings": move_warnings(moved, around)}

    @router.patch("/sessions/{session_id}")
    def update(session_id: int, body: Done, user_id: int = Depends(require_user), repo: Repo = Depends(get_repo)) -> dict[str, Any]:
        row = repo.update_session(user_id, session_id, body.status, clean_log(body.logged))
        if not row:
            raise HTTPException(404, "Séance inconnue.")
        return serialize(row)

    return router
