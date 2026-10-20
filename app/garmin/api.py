"""Connexion Garmin par utilisateur : le mot de passe sert une fois, seul un jeton chiffré est conservé."""
import logging
import time
from datetime import date, timedelta
from typing import Any

from fastapi import APIRouter, Depends, HTTPException, Request
from pydantic import BaseModel, Field

from app.auth import _check_rate, _fail
from app.garmin import crypto
from app.garmin.client import GarminAuthError, GarminGateway, GarminRateLimited, GarminUnavailable
from app.garmin.match import auto_link
from app.questionnaire.models import Fact
from app.repo import Repo

log = logging.getLogger("sport-coach.sync")
MFA_TTL = 600
HISTORY_DAYS, SYNC_DAYS = 730, 28  # historique conservé : 2 ans
_pending: dict[int, tuple[float, Any, str]] = {}  # utilisateur -> (expiration, handle MFA, email) ; en mémoire seulement


class Connect(BaseModel):
    email: str = Field(max_length=200)
    password: str = Field(max_length=200)


class Mfa(BaseModel):
    code: str = Field(min_length=4, max_length=12)


def _configured() -> bool:
    try:
        crypto._fernet()
        return True
    except crypto.NotConfigured:
        return False


def _derive_facts(repo: Repo, user_id: int, today: date) -> None:
    """Volume de course mesuré sur 8 semaines (fait de source garmin) : il remplace l'estimation déclarée.

    Dès que la montre a enregistré assez d'activités (6 sur 8 semaines, tous sports), l'absence de course est
    une information : 0 km mesuré est plus prudent qu'une estimation optimiste (règle de prudence du moteur).
    """
    year = repo.list_activities(user_id, today - timedelta(days=365), 5000)
    acts = [a for a in year if a["day"] >= today - timedelta(days=56)]
    facts: list[Fact] = []
    if len(acts) >= 6:
        km = round(sum(a["distance_m"] or 0 for a in acts if a["sport"] == "run") / 1000 / 8, 1)
        facts.append(Fact(key="running.weekly_km_8w", value=km, source="garmin"))
        runs8 = [a["duration_s"] for a in acts if a["sport"] == "run" and a["duration_s"]]
        if runs8:  # point de départ de la sortie longue d'un objectif (C9)
            facts.append(Fact(key="running.longest_recent_min", value=round(max(runs8) / 60), source="garmin"))
    if len(year) >= 20:  # historique suffisant : volume habituel sur 12 mois et ancienneté de la dernière course
        runs = [a for a in year if a["sport"] == "run"]
        facts.append(Fact(key="running.weekly_km_12m", value=round(sum(a["distance_m"] or 0 for a in runs) / 1000 / 52, 1), source="garmin"))
        last = max((a["day"] for a in runs), default=None)
        facts.append(Fact(key="running.weeks_since_last_run", value=(today - last).days // 7 if last else 99, source="garmin"))
        n_str = sum(1 for a in year if a["sport"] == "strength")
        if n_str >= 10:
            facts.append(Fact(key="strength.sessions_per_week_12m", value=round(n_str / 52, 1), source="garmin"))
    if facts:
        repo.add_facts(user_id, facts)


def _sync_metrics(repo: Repo, gateway: Any, user_id: int, acct: dict[str, Any], today: date) -> None:
    """Mesures quotidiennes ; secondaires : une erreur ne fait jamais échouer la synchronisation des activités."""
    fetch = getattr(gateway, "fetch_metrics", None)
    if not fetch:
        return
    try:
        first = not repo.list_metrics(user_id, "resting_hr", today - timedelta(days=HISTORY_DAYS))
        tokens = crypto.decrypt(repo.get_garmin(user_id)["tokens_enc"])
        rows, fresh = fetch(tokens, today - timedelta(days=HISTORY_DAYS if first else SYNC_DAYS), today, first)
        repo.upsert_metrics(user_id, rows)
        repo.touch_garmin(user_id, crypto.encrypt(fresh), None)
    except Exception as e:  # noqa: BLE001 - voir docstring
        log.warning("mesures Garmin : %s", type(e).__name__)


def sync_user(repo: Repo, gateway: Any, user_id: int, today: date | None = None) -> dict[str, Any]:
    today = today or date.today()
    acct = repo.get_garmin(user_id)
    if not acct:
        raise HTTPException(409, "Garmin n'est pas connecté.")
    backfill = acct.get("backfilled_at") is None  # première récupération complète (ou nouvelle connexion)
    try:
        tokens = crypto.decrypt(acct["tokens_enc"])
        rows, fresh = gateway.fetch_activities(tokens, today - timedelta(days=HISTORY_DAYS if backfill else SYNC_DAYS), today)
    except crypto.NotConfigured as e:
        raise HTTPException(503, str(e)) from e
    except GarminAuthError as e:
        repo.touch_garmin(user_id, None, "Connexion Garmin expirée : reconnectez-vous.")
        raise HTTPException(401, "Connexion Garmin expirée : reconnectez-vous.") from e
    except GarminRateLimited as e:
        raise HTTPException(429, "Garmin limite les requêtes. Réessayez plus tard.") from e
    except GarminUnavailable as e:
        raise HTTPException(502, "Garmin est injoignable pour le moment.") from e
    added = repo.upsert_activities(user_id, rows)
    repo.touch_garmin(user_id, crypto.encrypt(fresh), None)
    if backfill:
        repo.mark_backfilled(user_id)
    repo.prune_activities(user_id, today - timedelta(days=HISTORY_DAYS + 10))
    _sync_metrics(repo, gateway, user_id, acct, today)
    _derive_facts(repo, user_id, today)
    return {"fetched": len(rows), "added": added, "backfill": backfill, "sessions_completed": auto_link(repo, user_id, today, SYNC_DAYS)}  # pas d'auto-validation sur l'historique ancien


def build_router(get_repo: Any, require_user: Any) -> APIRouter:
    router = APIRouter(prefix="/users/{user_id}/garmin", tags=["garmin"])

    def gw(request: Request) -> Any:
        return request.app.state.garmin

    def status_of(user_id: int, repo: Repo) -> dict[str, Any]:
        acct = repo.get_garmin(user_id)
        recent = repo.list_activities(user_id, date.today() - timedelta(days=60), 12)
        total = len(repo.list_activities(user_id, date.today() - timedelta(days=HISTORY_DAYS), 5000))
        return {"configured": _configured(), "connected": bool(acct), "email": acct["email"] if acct else None,
                "last_sync_at": acct["last_sync_at"].isoformat() if acct and acct["last_sync_at"] else None,
                "last_error": acct["last_error"] if acct else None, "total_activities": total,
                "history_days": HISTORY_DAYS,
                "recent": [{**a, "day": a["day"].isoformat(), "started_at": None} for a in recent]}

    @router.get("")
    def status(user_id: int = Depends(require_user), repo: Repo = Depends(get_repo)) -> dict[str, Any]:
        return status_of(user_id, repo)

    def finish(user_id: int, email: str, tokens: str, repo: Repo, gateway: Any) -> dict[str, Any]:
        repo.save_garmin(user_id, email, crypto.encrypt(tokens))
        result = sync_user(repo, gateway, user_id)
        return {"status": "connected", **result}

    @router.post("/connect")
    def connect(body: Connect, user_id: int = Depends(require_user), repo: Repo = Depends(get_repo),
                gateway: Any = Depends(gw)) -> dict[str, Any]:
        if not _configured():
            raise HTTPException(503, "La connexion Garmin n'est pas configurée sur ce serveur.")
        key = f"garmin|{user_id}"
        _check_rate(key)
        email = body.email.strip()
        try:
            res = gateway.start_login(email, body.password)
        except GarminAuthError as e:
            _fail(key)
            raise HTTPException(401, "Identifiants Garmin refusés.") from e
        except GarminRateLimited as e:
            raise HTTPException(429, "Garmin limite les connexions. Réessayez plus tard.") from e
        except GarminUnavailable as e:
            raise HTTPException(502, "Garmin est injoignable pour le moment.") from e
        if res.mfa_handle is not None:
            _pending[user_id] = (time.time() + MFA_TTL, res.mfa_handle, email)
            return {"status": "mfa_required"}
        return finish(user_id, email, res.tokens, repo, gateway)

    @router.post("/mfa")
    def mfa(body: Mfa, user_id: int = Depends(require_user), repo: Repo = Depends(get_repo),
            gateway: Any = Depends(gw)) -> dict[str, Any]:
        pend = _pending.get(user_id)
        if not pend or pend[0] < time.time():
            _pending.pop(user_id, None)
            raise HTTPException(409, "La demande de code a expiré : recommencez la connexion.")
        _check_rate(f"garmin-mfa|{user_id}")
        try:
            res = gateway.finish_mfa(pend[1], body.code)
        except GarminAuthError as e:
            _fail(f"garmin-mfa|{user_id}")
            raise HTTPException(401, "Code refusé.") from e
        except GarminRateLimited as e:
            raise HTTPException(429, "Garmin limite les connexions. Réessayez plus tard.") from e
        except GarminUnavailable as e:
            raise HTTPException(502, "Garmin est injoignable pour le moment.") from e
        _pending.pop(user_id, None)
        return finish(user_id, pend[2], res.tokens, repo, gateway)

    @router.post("/sync")
    def sync(user_id: int = Depends(require_user), repo: Repo = Depends(get_repo), gateway: Any = Depends(gw)) -> dict[str, Any]:
        return sync_user(repo, gateway, user_id)

    @router.delete("")
    def disconnect(purge: bool = False, user_id: int = Depends(require_user), repo: Repo = Depends(get_repo)) -> dict[str, bool]:
        repo.delete_garmin(user_id, purge)
        _pending.pop(user_id, None)
        return {"ok": True}

    return router


def default_gateway() -> GarminGateway:
    return GarminGateway()
