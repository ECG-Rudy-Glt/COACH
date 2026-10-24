"""API du plan : génération, lecture, réalisation d'une séance."""
import hashlib
import json
from datetime import date, timedelta
from typing import Any, Literal

from fastapi import APIRouter, Depends, HTTPException, Request
from pydantic import BaseModel, Field

from app.coach.replan_explain import explain
from app.garmin.match import auto_link, link_fields, suggestions, unlink_fields
from app.plan import trajectory
from app.plan.cycles import continue_anchor, describe
from app.plan.engine import KEY, advice, build_profile, empty_reason, outlook, plan_weeks, warnings
from app.plan.level import with_estimates
from app.plan.pain import pain_zones
from app.plan.replan import replan_rest_of_week
from app.plan.strength import annotate_history, resolve
from app.questionnaire.models import current_facts
from app.repo import Repo


class Generate(BaseModel):
    weeks: int = Field(default=1, ge=1, le=8)  # une semaine à la fois : le coach a lu les retours avant la suivante
    restart_cycle: bool = False  # démarrer un nouveau cycle (sinon le cycle en cours continue)


class ReplanIn(BaseModel):
    include_today: bool = False  # par défaut, la séance d'aujourd'hui est considérée comme non faisable : on replanifie à partir de demain
    explain: bool = False  # une phrase d'explication par l'IA si elle est configurée (jamais de chiffre)


class ReplanApply(BaseModel):
    include_today: bool = False
    fingerprint: str = Field(min_length=8, max_length=64)  # empreinte de l'aperçu accepté : si le plan a changé entre-temps, rien n'est appliqué


REPLAN_KIND = "replan_week"


def load_profile(repo: Repo, user_id: int, today: date) -> tuple[dict[str, Any], list[dict[str, Any]], Any]:
    """Faits (douleur d'un retour de séance = blessure active, S2), objectifs et profil du moteur, comme pour la génération du plan."""
    facts = {k: v for k, v in current_facts(repo.list_facts(user_id)).items() if v is not None}
    zones = pain_zones(repo.list_sessions(user_id, today - timedelta(days=21), today), today)
    if zones:
        facts = {**facts, "history.injuries": sorted({*(facts.get("history.injuries") or []), *zones} - {"aucune"})}
    goals = repo.list_goals(user_id, None)
    facts = estimated_facts(repo, user_id, facts, goals, today)
    return facts, goals, build_profile(facts, goals, today)


def fingerprint_of(proposal: dict[str, Any]) -> str:
    keep = {"from": proposal["from"], "changes": [(c["session_id"], c["to"], c["duration_to"]) for c in proposal["changes"]]}
    return hashlib.sha256(json.dumps(keep, sort_keys=True).encode()).hexdigest()[:24]


def compute_replan(repo: Repo, user_id: int, today: date, include_today: bool) -> dict[str, Any]:
    _, _, prof = load_profile(repo, user_id, today)
    monday = today - timedelta(days=today.weekday())
    rows = repo.list_sessions(user_id, monday - timedelta(days=1), monday + timedelta(days=8))
    acts = [{"day": date.fromisoformat(a["day"]), "minutes": round((a["duration_s"] or 0) / 60), "run": a["sport"] == "run"}
            for a in week_activities(repo, user_id, monday, [r for r in rows if monday <= r["day"] < monday + timedelta(days=7)])]
    avoid: set[date] = set()
    try:  # W7 : météo optionnelle, échec silencieux (W8) ; jamais bloquant
        from app.weather import service as weather
        avoid = {date.fromisoformat(i["day"]) for i in weather.outlook(repo, user_id, today)["items"] if i["status"] == "avoid"}
    except Exception:  # noqa: BLE001
        avoid = set()
    out = replan_rest_of_week(prof, rows, acts, today, avoid, include_today)
    out["fingerprint"] = fingerprint_of(out)
    return out


def with_sources(out: dict[str, Any], evidence: list[dict[str, Any]]) -> dict[str, Any]:
    by_id = {e["id"]: e for e in evidence}
    for a in out["applied"]:
        a["sources"] = [{"id": i, "citation": by_id[i]["citation"], "url": by_id[i]["url"]} for i in a["ids"] if i in by_id]
    return out


def snapshot(r: dict[str, Any]) -> dict[str, Any]:
    return {"id": r["id"], "day": r["day"].isoformat(), "duration_min": r["duration_min"], "notes": list(r["notes"] or []), "details": r["details"] or {}, "status": r["status"]}


def last_replan(repo: Repo, user_id: int, monday: date) -> dict[str, Any] | None:
    """Dernière replanification non annulée de la semaine en cours : l'écran propose de l'annuler."""
    m = next((m for m in repo.list_memory(user_id, REPLAN_KIND, 5) if m["period_start"] == monday and not (m["data"] or {}).get("undone")), None)
    return {"id": m["id"], "changed": len((m["data"] or {}).get("after", []))} if m else None


MOVE_PAST_DAYS = 56  # on ne rattache pas une séance à plus de 8 semaines en arrière
MOVE_FUTURE_DAYS = 120
ALLOWED_LOG = {"rpe", "minutes", "note", "adaptation", "changes", "exercises", "source", "garmin_id", "distance_km", "avg_hr", "max_hr", "calories", "training_load", "garmin_name", "pace_s_km"}  # noqa: E501
NUMERIC_LOG = {"rpe": (1, 10), "minutes": (1, 1500), "distance_km": (0.1, 1000), "avg_hr": (30, 250), "max_hr": (30, 250)}
CHANGES = {"plus léger", "plus court", "plus long", "exercice remplacé", "séries en moins", "séries en plus", "douleur", "trop facile", "trop dur", "matériel manquant"}


def estimated_facts(repo: Repo, user_id: int, facts: dict[str, Any], goals: list[dict[str, Any]], today: date) -> dict[str, Any]:
    """Faits + niveau récent estimé (C14, C15) d'après les sorties de la montre et les charges saisies."""
    acts = repo.list_activities(user_id, today - timedelta(days=56), 500)
    sess = repo.list_sessions(user_id, today - timedelta(days=84), today + timedelta(days=1))
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
    for k, (lo, hi) in NUMERIC_LOG.items():  # valeurs saisies à la main : bornées, sinon ignorées (jamais d'erreur pour un champ facultatif)
        if k in out:
            v = out[k]
            if isinstance(v, bool) or not isinstance(v, int | float) or not lo <= v <= hi:
                del out[k]
    if out.get("distance_km") and out.get("minutes") and not out.get("garmin_id"):
        out["pace_s_km"] = round(out["minutes"] * 60 / out["distance_km"])  # allure moyenne déduite des deux mesures saisies, jamais fournie par le client
    elif "pace_s_km" in out and not out.get("garmin_id"):
        del out["pace_s_km"]
    if "changes" in out:
        out["changes"] = [c for c in (out["changes"] if isinstance(out["changes"], list) else []) if c in CHANGES][:8]
    return out


class Link(BaseModel):
    garmin_id: str = Field(min_length=1, max_length=40)
    move: bool = True  # activité faite un autre jour : la séance suit l'activité


class Move(BaseModel):
    day: date


# séance faite hors plan (ex. un « dos biceps » improvisé) : saisie par l'utilisateur, jamais générée ni modifiée par le moteur
MANUAL_TITLES = {"strength_upper": "Haut du corps", "strength_lower": "Jambes", "strength_full": "Musculation", "strength_crossfit": "CrossFit",
                 "run_easy": "Course facile", "run_long": "Sortie longue", "run_quality": "Course qualité",
                 "sport_bike": "Vélo", "sport_swim": "Natation", "sport_walk": "Marche", "sport_other": "Autre sport"}


class Manual(BaseModel):
    day: date
    kind: Literal["strength_upper", "strength_lower", "strength_full", "strength_crossfit", "run_easy", "run_long", "run_quality",
                  "sport_bike", "sport_swim", "sport_walk", "sport_other"]
    title: str = Field(default="", max_length=80)
    duration_min: int = Field(ge=5, le=600)
    logged: dict[str, Any] | None = None


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
        facts, goals, profile = load_profile(repo, user_id, today)
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
                "cycle": describe(rows, today), "trajectory": trajectory.describe(prof.target, facts, goals, today), "replan": last_replan(repo, user_id, start)}

    @router.post("/replan/preview")
    def replan_preview(request: Request, body: ReplanIn | None = None, user_id: int = Depends(require_user), repo: Repo = Depends(get_repo)) -> dict[str, Any]:
        """Aperçu de la fin de semaine replanifiée (G13 à G17) : ne modifie rien. La phrase d'IA est facultative et ne porte aucun chiffre."""
        b = body or ReplanIn()
        out = with_sources(compute_replan(repo, user_id, date.today(), b.include_today), request.app.state.evidence)
        out["explanation"] = explain(repo, request.app.state.llm, user_id, out, out["fingerprint"]) if b.explain else None
        return out

    @router.post("/replan/apply")
    def replan_apply(body: ReplanApply, user_id: int = Depends(require_user), repo: Repo = Depends(get_repo)) -> dict[str, Any]:
        """Applique la proposition recalculée côté serveur (jamais celle envoyée par le client) si elle est identique à l'aperçu accepté ; trace annulable."""
        today = date.today()
        out = compute_replan(repo, user_id, today, body.include_today)
        if out["empty"]:
            raise HTTPException(409, "Rien à replanifier.")
        if out["fingerprint"] != body.fingerprint:
            raise HTTPException(409, "Le plan a changé depuis l'aperçu : relancez la replanification.")
        monday = today - timedelta(days=today.weekday())
        rows = {r["id"]: r for r in repo.list_sessions(user_id, monday, monday + timedelta(days=7))}
        touched = [c for c in out["changes"] if c["action"] != "keep"]
        before = [snapshot(rows[c["session_id"]]) for c in touched if c["session_id"] in rows]
        rule_ids = [a["rule"] for a in out["applied"]]
        for c in touched:
            r = rows.get(c["session_id"])
            if not r or r["status"] != "planned":
                continue
            note = f"Replanifiée ({', '.join(rule_ids)})" if c["action"] != "drop" else f"Retirée de la semaine par la replanification ({', '.join(rule_ids)})"
            changes: dict[str, Any] = {"notes": [*r["notes"], note]}
            if c["action"] != "drop":
                changes["duration_min"] = c["duration_to"]
                if c["to"] != r["day"].isoformat():
                    changes["day"] = date.fromisoformat(c["to"])
                    changes["details"] = {**(r["details"] or {}), "moved_from": (r["details"] or {}).get("moved_from") or r["day"].isoformat()}
            repo.patch_planned(user_id, r["id"], changes)
            if c["action"] == "drop":
                repo.update_session(user_id, r["id"], "skipped", None)
        mem = repo.add_memory(user_id, REPLAN_KIND, (monday, monday + timedelta(days=6)), f"Replanification de la fin de semaine ({', '.join(rule_ids)})",
                              {"before": before, "after": touched, "rules": rule_ids, "undone": False})
        return {"id": mem["id"], "changed": len(touched)}

    @router.post("/replan/{memory_id}/undo")
    def replan_undo(memory_id: int, user_id: int = Depends(require_user), repo: Repo = Depends(get_repo)) -> dict[str, Any]:
        mem = repo.get_memory(user_id, memory_id)
        if not mem or mem["kind"] != REPLAN_KIND:
            raise HTTPException(404, "Replanification inconnue.")
        data = mem["data"] or {}
        if data.get("undone"):
            raise HTTPException(409, "Cette replanification est déjà annulée.")
        monday = mem["period_start"]
        rows = {r["id"]: r for r in repo.list_sessions(user_id, monday, monday + timedelta(days=7))}
        if any(s["id"] not in rows or rows[s["id"]]["status"] == "done" for s in data.get("before", [])):
            raise HTTPException(409, "Une séance a été faite depuis : l'annulation n'est plus possible.")
        for s in data.get("before", []):
            if s["status"] == "planned" and rows[s["id"]]["status"] != "planned":
                repo.update_session(user_id, s["id"], "planned", None)
            repo.patch_planned(user_id, s["id"], {"day": date.fromisoformat(s["day"]), "duration_min": s["duration_min"], "notes": s["notes"], "details": s["details"]})
        repo.update_memory_data(user_id, memory_id, {**data, "undone": True})
        return {"restored": len(data.get("before", []))}

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

    @router.post("/sessions", status_code=201)
    def add_manual(body: Manual, user_id: int = Depends(require_user), repo: Repo = Depends(get_repo)) -> dict[str, Any]:
        """Ajoute une séance déjà faite hors plan. Statut « faite » : une régénération du plan (qui ne remplace que les séances « planned ») la garde."""
        today = date.today()
        if not today - timedelta(days=MOVE_PAST_DAYS) <= body.day <= today:
            raise HTTPException(422, "Une séance ajoutée doit être déjà faite : aujourd'hui ou dans les 8 dernières semaines.")
        title = " ".join(body.title.split()) or MANUAL_TITLES[body.kind]
        row = repo.add_session(user_id, {"day": body.day, "kind": body.kind, "title": title, "duration_min": body.duration_min, "details": {"manual": True},
                                            "rules": [], "notes": [], "status": "done", "logged": {**(clean_log(body.logged) or {}), "source": "manual"}})
        return serialize(row)

    @router.delete("/sessions/{session_id}")
    def delete_manual(session_id: int, user_id: int = Depends(require_user), repo: Repo = Depends(get_repo)) -> dict[str, bool]:
        row = find_session(repo, user_id, session_id, date.today())
        if not (row.get("details") or {}).get("manual"):
            raise HTTPException(409, "Seule une séance ajoutée à la main peut être supprimée ; une séance du plan se passe.")
        return {"deleted": repo.remove_session(user_id, session_id)}

    @router.patch("/sessions/{session_id}")
    def update(session_id: int, body: Done, user_id: int = Depends(require_user), repo: Repo = Depends(get_repo)) -> dict[str, Any]:
        row = repo.update_session(user_id, session_id, body.status, clean_log(body.logged))
        if not row:
            raise HTTPException(404, "Séance inconnue.")
        return serialize(row)

    return router
