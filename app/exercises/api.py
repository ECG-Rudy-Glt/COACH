"""Bibliothèque d'exercices : recherche, fiche, médias en cache local (jamais d'URL libre fournie par le client)."""
import hashlib
import os
import urllib.request
from pathlib import Path
from typing import Any
from urllib.parse import urlparse

from fastapi import APIRouter, Depends, HTTPException, Response

from app.exercises.labels import EQUIPMENT_FR, KIND_FR, MUSCLE_FR
from app.exercises.models import Exercise
from app.repo import Repo

ALLOWED_HOSTS = {"wger.de", "raw.githubusercontent.com"}
MAX_IMAGE = 8 * 1024 * 1024
MEDIA_DIR = Path(os.environ.get("MEDIA_DIR", "/tmp/sport-coach-media"))
CONTENT = {".webp": "image/webp", ".png": "image/png", ".jpg": "image/jpeg", ".jpeg": "image/jpeg",
           ".gif": "image/gif"}


def _summary(e: Exercise) -> dict[str, Any]:
    main = next((m for m in e.media if m.kind == "image"), None)
    return {"id": e.id, "name": e.name, "kind": e.kind, "muscles_primary": e.muscles_primary,
            "equipment": e.equipment, "thumb": main.id if main else None}


def _fetch_image(url: str) -> bytes:
    host = urlparse(url).hostname or ""
    if urlparse(url).scheme != "https" or host not in ALLOWED_HOSTS:
        raise HTTPException(502, "Source de média non autorisée.")
    req = urllib.request.Request(url, headers={"User-Agent": "sport-coach/0.1"})
    with urllib.request.urlopen(req, timeout=15) as r:  # noqa: S310 : hôte et schéma contrôlés ci-dessus
        data = r.read(MAX_IMAGE + 1)
    if len(data) > MAX_IMAGE:
        raise HTTPException(502, "Média trop volumineux.")
    return data


def build_router(get_repo: Any, current_user: Any) -> APIRouter:
    router = APIRouter(tags=["exercices"], dependencies=[Depends(current_user)])

    @router.get("/exercises/meta")
    def meta() -> dict[str, dict[str, str]]:
        return {"muscles": MUSCLE_FR, "equipment": EQUIPMENT_FR, "kinds": KIND_FR}

    @router.get("/exercises")
    def search(q: str | None = None, muscle: str | None = None, equipment: str | None = None,
               kind: str | None = None, limit: int = 30, offset: int = 0,
               repo: Repo = Depends(get_repo)) -> dict[str, Any]:
        limit = max(1, min(limit, 100))
        rows, total = repo.search_exercises((q or "").strip()[:60] or None, muscle, equipment, kind, limit,
                                            max(0, offset))
        return {"total": total, "items": [_summary(e) for e in rows]}

    @router.get("/exercises/{exercise_id}")
    def detail(exercise_id: int, repo: Repo = Depends(get_repo)) -> dict[str, Any]:
        e = repo.get_exercise(exercise_id)
        if not e:
            raise HTTPException(404, "Exercice inconnu.")
        d = e.model_dump(exclude={"media"})
        d["media"] = [{"id": m.id, "kind": m.kind, "license": m.license, "license_url": m.license_url,
                       "author": m.author, "is_main": m.is_main,
                       "video_url": m.url if m.kind == "video" else None} for m in e.media]
        return d

    @router.get("/media/{media_id}")
    def media(media_id: int, repo: Repo = Depends(get_repo)) -> Response:
        m = repo.get_media(media_id)
        if not m or m.kind != "image":
            raise HTTPException(404, "Média inconnu.")
        url = m.thumb_url or m.url
        ext = Path(urlparse(url).path).suffix.lower()
        ctype = CONTENT.get(ext)
        if not ctype:
            raise HTTPException(502, "Format de média non pris en charge.")
        MEDIA_DIR.mkdir(parents=True, exist_ok=True)
        path = MEDIA_DIR / (hashlib.sha256(url.encode()).hexdigest() + ext)
        if not path.exists():
            try:
                data = _fetch_image(url)
            except HTTPException:
                raise
            except Exception as e:  # réseau, TLS, 404 distant…
                raise HTTPException(502, "Média indisponible pour le moment.") from e
            path.write_bytes(data)
        return Response(path.read_bytes(), media_type=ctype,
                        headers={"Cache-Control": "private, max-age=2592000, immutable"})

    return router
