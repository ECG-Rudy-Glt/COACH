"""Courbes d'une séance reliée à une activité (règles ST25 à ST28) : tout est calculé ici à partir des séries stockées, jamais par un LLM. Aucune latitude ni longitude."""
import logging
from datetime import date, timedelta
from typing import Any

from fastapi import APIRouter, Depends, HTTPException, Request

from app.activity_import.streams import parse_streams
from app.auth import _check_rate, _fail
from app.curves import zones as Z
from app.garmin import crypto
from app.garmin.client import GarminAuthError, GarminRateLimited, GarminUnavailable
from app.plan.api import find_session
from app.plan.level import _hr_max
from app.questionnaire.models import current_facts
from app.repo import Repo

log = logging.getLogger("sport-coach.curves")
MAX_FETCH_PER_WINDOW = 12  # téléchargements Garmin par utilisateur et par fenêtre d'une quinzaine de minutes (auth.WINDOW)
LOOKBACK_DAYS = 120


def _activity(repo: Repo, user_id: int, row: dict[str, Any], gid: str) -> dict[str, Any] | None:
    since = min(row["day"], date.today()) - timedelta(days=LOOKBACK_DAYS)
    return next((a for a in repo.list_activities(user_id, since, 5000) if a["garmin_id"] == gid), None)


def _hr_basis(repo: Repo, user_id: int, activities: list[dict[str, Any]]) -> tuple[float | None, str | None]:
    facts = {k: v for k, v in current_facts(repo.list_facts(user_id)).items() if v is not None}
    hr_max = _hr_max(facts, activities)
    declared = isinstance(facts.get("running.hr_max"), int | float) and not isinstance(facts.get("running.hr_max"), bool) and facts["running.hr_max"] > 100
    return hr_max, ("declared" if declared else "observed") if hr_max else None


def summary(row: dict[str, Any], act: dict[str, Any]) -> dict[str, Any]:
    """Prévu / fait côte à côte (ST28) : le moteur prévoit une durée (et parfois une distance), la montre mesure ; l'écart est donné, jamais jugé."""
    planned_min = row.get("duration_min")
    done_min = round((act.get("duration_s") or 0) / 60) or None
    dist_km = round(act["distance_m"] / 1000, 2) if act.get("distance_m") else None
    plan_km = (row.get("details") or {}).get("distance_km")
    plan_km = float(plan_km) if isinstance(plan_km, int | float) and not isinstance(plan_km, bool) and plan_km > 0 else None
    manual = bool((row.get("details") or {}).get("manual"))
    return {"title": row["title"], "manual": manual,
            "planned": None if manual else {"minutes": planned_min, "distance_km": plan_km},
            "done": {"minutes": done_min, "distance_km": dist_km, "avg_hr": act.get("avg_hr"), "max_hr": act.get("max_hr"),
                     "elevation_m": round(act["elevation_m"]) if act.get("elevation_m") else None,
                     "pace_s_km": round((act["duration_s"] or 0) / (act["distance_m"] / 1000)) if act.get("distance_m") and act.get("duration_s") and act["distance_m"] >= 1000 else None},
            "gap_minutes": None if manual or not planned_min or not done_min else done_min - planned_min}


def view(repo: Repo, user_id: int, row: dict[str, Any]) -> dict[str, Any]:
    gid = (row.get("logged") or {}).get("garmin_id")
    if not gid:
        return {"available": False, "reason": "no_activity"}
    act = _activity(repo, user_id, row, gid)
    if not act:
        return {"available": False, "reason": "no_activity"}
    streams = repo.get_streams(user_id, gid)
    if not streams:
        can = act.get("source") == "garmin" and gid.isdigit() and repo.get_garmin(user_id) is not None
        return {"available": False, "reason": "no_streams", "can_fetch": can, "source": act.get("source"), "summary": summary(row, act)}
    hr_max, basis = _hr_basis(repo, user_id, repo.list_activities(user_id, date.today() - timedelta(days=365), 5000))
    return {"available": True, "source": act.get("source"), "sport": act["sport"], "n": streams["n"], "duration_s": streams["duration_s"],
            **{k: streams[k] for k in ("t", "dist", "hr", "speed", "alt", "cad", "power", "splits")},
            "zones": Z.zones_block(streams, hr_max, basis), "summary": summary(row, act)}


def build_router(get_repo: Any, require_user: Any) -> APIRouter:
    router = APIRouter(prefix="/users/{user_id}/plan/sessions/{session_id}/curves", tags=["curves"])

    @router.get("")
    def curves(session_id: int, user_id: int = Depends(require_user), repo: Repo = Depends(get_repo)) -> dict[str, Any]:
        return view(repo, user_id, find_session(repo, user_id, session_id, date.today()))

    @router.post("/fetch")
    def fetch(session_id: int, request: Request, user_id: int = Depends(require_user), repo: Repo = Depends(get_repo)) -> dict[str, Any]:
        """Télécharge à la demande le détail d'une activité Garmin (fichier TCX), en garde les courbes sans position GPS et jette le fichier."""
        row = find_session(repo, user_id, session_id, date.today())
        gid = (row.get("logged") or {}).get("garmin_id") or ""
        act = _activity(repo, user_id, row, gid) if gid else None
        if not act:
            raise HTTPException(404, "Aucune activité reliée à cette séance.")
        if repo.get_streams(user_id, gid):
            return view(repo, user_id, row)
        acct = repo.get_garmin(user_id)
        gateway = request.app.state.garmin
        if act.get("source") != "garmin" or not gid.isdigit() or not acct or not hasattr(gateway, "download_activity_tcx"):
            raise HTTPException(409, "Le détail n'est disponible à la demande que pour une activité synchronisée depuis Garmin.")
        key = f"curves|{user_id}"
        _check_rate(key, MAX_FETCH_PER_WINDOW)
        _fail(key)
        try:
            raw, fresh = gateway.download_activity_tcx(crypto.decrypt(acct["tokens_enc"]), gid)
        except crypto.NotConfigured as e:
            raise HTTPException(503, str(e)) from e
        except GarminAuthError as e:
            repo.touch_garmin(user_id, None, "Connexion Garmin expirée : reconnectez-vous.")
            raise HTTPException(401, "Connexion Garmin expirée : reconnectez-vous.") from e
        except GarminRateLimited as e:
            raise HTTPException(429, "Garmin limite les requêtes. Réessayez plus tard.") from e
        except GarminUnavailable as e:
            raise HTTPException(502, "Garmin est injoignable pour le moment.") from e
        repo.touch_garmin(user_id, crypto.encrypt(fresh), None)
        streams = parse_streams(raw)
        if not streams:
            raise HTTPException(422, "Cette activité n'a pas de courbes exploitables (pas de mesures enregistrées au fil du temps).")
        repo.save_streams(user_id, gid, streams)
        return view(repo, user_id, row)

    return router
