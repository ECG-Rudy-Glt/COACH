"""Import d'activités depuis des fichiers FIT, TCX et GPX (toutes marques) : les lignes rejoignent celles de la montre Garmin.

Envoi en JSON/base64 (comme la photo d'un repas, sans dépendance multipart). Les traces GPS ne quittent jamais le serveur et ne sont pas
conservées : seuls les totaux de la séance et des courbes simplifiées (FC, vitesse, altitude, cadence, puissance, sans latitude ni longitude) sont gardés.
"""
import base64
import binascii
import logging
from datetime import UTC, date, timedelta, tzinfo
from typing import Any
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError

from fastapi import APIRouter, Depends
from pydantic import BaseModel, Field

from app.activity_import.parse import MAX_FILE_BYTES, ImportRejected, is_duplicate, parse_activity, too_old
from app.activity_import.streams import parse_streams
from app.garmin.api import HISTORY_DAYS, SYNC_DAYS, _derive_facts
from app.garmin.match import auto_link
from app.repo import Repo

log = logging.getLogger("sport-coach.import")
MAX_FILES = 20
MAX_REQUEST_BYTES = 60 * 1024 * 1024  # octets décodés cumulés par envoi


class FileIn(BaseModel):
    name: str = Field(default="", max_length=300)
    data: str = Field(max_length=16_000_000)  # base64 ; la taille décodée est vérifiée fichier par fichier


class ImportIn(BaseModel):
    files: list[FileIn] = Field(min_length=1, max_length=MAX_FILES)
    tz: str | None = Field(default=None, max_length=64)  # fuseau IANA du navigateur : les fichiers sont en UTC, la séance est datée en heure locale


def _zone(name: str | None) -> tzinfo:
    try:
        return ZoneInfo(name) if name else UTC
    except (ZoneInfoNotFoundError, ValueError, OSError):
        return UTC


def _decode(data: str) -> bytes:
    if len(data) * 3 // 4 > MAX_FILE_BYTES + 3:
        raise ImportRejected("Fichier trop volumineux (10 Mo maximum).")
    try:
        return base64.b64decode(data.split(",", 1)[-1], validate=True)
    except (binascii.Error, ValueError) as e:
        raise ImportRejected("Fichier illisible.") from e


def import_files(repo: Repo, user_id: int, files: list[FileIn], tz: tzinfo = UTC, today: date | None = None) -> dict[str, Any]:
    today = today or date.today()
    existing = repo.list_activities(user_id, today - timedelta(days=HISTORY_DAYS + 1), 5000)
    results: list[dict[str, Any]] = []
    budget = MAX_REQUEST_BYTES
    for f in files:
        name = "".join(ch for ch in f.name.replace("\\", "/").rsplit("/", 1)[-1] if ch.isprintable())[:80]  # affichage seulement : jamais un chemin
        res: dict[str, Any] = {"name": name, "status": "rejected", "message": None, "activity": None}
        results.append(res)
        try:
            raw = _decode(f.data)
            budget -= len(raw)
            if budget < 0:
                raise ImportRejected("Envoi trop volumineux : réessayez avec moins de fichiers à la fois.")
            row = parse_activity(raw, tz)
            if too_old(row["day"], today, HISTORY_DAYS):
                raise ImportRejected("Activité de plus de 2 ans : non conservée.")
            if row["day"] > today + timedelta(days=1):
                raise ImportRejected("Date dans le futur : fichier ignoré.")
        except ImportRejected as e:
            res["message"] = str(e)
            continue
        res["activity"] = {k: (row[k].isoformat() if k == "day" else row[k]) for k in ("day", "sport", "duration_s", "distance_m", "avg_hr", "source")}
        if is_duplicate(row, existing):
            res["status"] = "duplicate"
            res["message"] = "Déjà présente (même fichier ou même séance)."
            continue
        repo.upsert_activities(user_id, [row])
        streams = parse_streams(raw)  # courbes simplifiées sans position GPS (ST25) ; l'absence de courbe n'empêche jamais l'import
        if streams:
            repo.save_streams(user_id, row["garmin_id"], streams)
        existing.append({**row, "user_id": user_id})
        res["status"] = "imported"
    imported = sum(r["status"] == "imported" for r in results)
    completed = 0
    if imported:
        _derive_facts(repo, user_id, today)
        completed = auto_link(repo, user_id, today, SYNC_DAYS)
    return {"results": results, "imported": imported, "duplicates": sum(r["status"] == "duplicate" for r in results),
            "rejected": sum(r["status"] == "rejected" for r in results), "sessions_completed": completed}


def build_router(get_repo: Any, require_user: Any) -> APIRouter:
    router = APIRouter(prefix="/users/{user_id}/activities", tags=["import"])

    @router.post("/import")
    def import_activities(body: ImportIn, user_id: int = Depends(require_user), repo: Repo = Depends(get_repo)) -> dict[str, Any]:
        return import_files(repo, user_id, body.files, _zone(body.tz))

    return router
