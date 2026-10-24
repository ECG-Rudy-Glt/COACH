"""API météo : réglages (ville, activation, heure habituelle), recherche de ville et perspective des séances en extérieur."""
import threading
import time
from datetime import date
from typing import Any

from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import BaseModel, Field

from app.repo import Repo
from app.weather import client, service

GEOCODE_PER_HOUR = 30
_calls: dict[int, list[float]] = {}
_lock = threading.Lock()


class Place(BaseModel):
    name: str = Field(default="", max_length=80)
    lat: float = Field(ge=-90, le=90)
    lon: float = Field(ge=-180, le=180)


class Settings(BaseModel):
    enabled: bool | None = None
    hour: int | None = Field(default=None, ge=0, le=23)


def build_router(get_repo: Any, require_user: Any) -> APIRouter:
    router = APIRouter(prefix="/users/{user_id}/weather", tags=["weather"])

    @router.get("/settings")
    def get_settings(user_id: int = Depends(require_user), repo: Repo = Depends(get_repo)) -> dict[str, Any]:
        return service.settings(repo, user_id)

    @router.put("/settings")
    def put_settings(body: Settings, user_id: int = Depends(require_user), repo: Repo = Depends(get_repo)) -> dict[str, Any]:
        if body.enabled and not service.settings(repo, user_id)["place"]:
            raise HTTPException(422, "Indiquez d'abord votre ville pour activer la météo.")
        values = {k: v for k, v in body.model_dump().items() if v is not None}
        if values:
            service.save(repo, user_id, **values)
        return service.settings(repo, user_id)

    @router.put("/place")
    def put_place(body: Place, user_id: int = Depends(require_user), repo: Repo = Depends(get_repo)) -> dict[str, Any]:
        if not client.server_enabled():
            raise HTTPException(503, "La météo est désactivée sur ce serveur.")
        return service.set_place(repo, user_id, body.name, body.lat, body.lon)

    @router.delete("/place")
    def delete_place(user_id: int = Depends(require_user), repo: Repo = Depends(get_repo)) -> dict[str, Any]:
        return service.clear_place(repo, user_id)

    @router.get("/geocode")
    def geocode(q: str = Query(min_length=2, max_length=80), user_id: int = Depends(require_user)) -> dict[str, Any]:
        if not client.server_enabled():
            raise HTTPException(503, "La météo est désactivée sur ce serveur.")
        now = time.time()
        with _lock:
            recent = [t for t in _calls.get(user_id, []) if now - t < 3600]
            if len(recent) >= GEOCODE_PER_HOUR:
                raise HTTPException(429, "Trop de recherches de ville. Réessayez plus tard.")
            _calls[user_id] = [*recent, now]
        return {"results": client.geocode(q)}

    @router.get("/outlook")
    def outlook(user_id: int = Depends(require_user), repo: Repo = Depends(get_repo)) -> dict[str, Any]:
        return service.outlook(repo, user_id, date.today())

    return router
