"""Objectifs vivants : ajout, modification, clôture à tout moment."""
from datetime import date
from typing import Any, Literal

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, Field

from app.repo import Repo

Kind = Literal["event", "performance", "body", "health", "habit", "other"]
Priority = Literal["principal", "important", "si possible"]
Status = Literal["active", "done", "dropped"]
DETAIL_KEYS = {"sport", "distance_km", "elevation_m", "target_value", "unit"}


class GoalIn(BaseModel):
    title: str = Field(min_length=1, max_length=160)
    kind: Kind = "other"
    target_date: date | None = None
    priority: Priority = "important"
    success: str | None = Field(default=None, max_length=300)
    details: dict[str, Any] = Field(default_factory=dict)


class GoalPatch(BaseModel):
    title: str | None = Field(default=None, min_length=1, max_length=160)
    kind: Kind | None = None
    target_date: date | None = None
    clear_date: bool = False
    priority: Priority | None = None
    success: str | None = Field(default=None, max_length=300)
    details: dict[str, Any] | None = None
    status: Status | None = None


def clean_details(d: dict[str, Any]) -> dict[str, Any]:
    out = {}
    for k, v in d.items():
        if k not in DETAIL_KEYS:
            raise HTTPException(422, f"Détail inconnu : {k}")
        if isinstance(v, bool) or not isinstance(v, str | int | float):
            raise HTTPException(422, f"Détail invalide : {k}")
        if isinstance(v, str):
            v = v.strip()[:80]
        elif v < 0 or v > 100000:
            raise HTTPException(422, f"Détail hors limites : {k}")
        out[k] = v
    return out


def conflicts(goals: list[dict[str, Any]]) -> list[dict[str, Any]]:
    """Objectifs « événement » actifs à moins de 6 semaines l'un de l'autre."""
    ev = sorted((g for g in goals if g["status"] == "active" and g["kind"] == "event" and g["target_date"]),
                key=lambda g: g["target_date"])
    return [{"a": a["id"], "b": b["id"], "days": (b["target_date"] - a["target_date"]).days}
            for a, b in zip(ev, ev[1:], strict=False) if (b["target_date"] - a["target_date"]).days < 42]


def build_router(get_repo: Any, require_user: Any) -> APIRouter:
    router = APIRouter(prefix="/users/{user_id}/goals", tags=["objectifs"])

    @router.get("")
    def list_goals(status: Status | None = None, user_id: int = Depends(require_user),
                   repo: Repo = Depends(get_repo)) -> dict[str, Any]:
        goals = repo.list_goals(user_id, None)
        shown = [g for g in goals if status is None or g["status"] == status]
        return {"goals": shown, "conflicts": conflicts(goals)}

    @router.post("", status_code=201)
    def add_goal(body: GoalIn, user_id: int = Depends(require_user),
                 repo: Repo = Depends(get_repo)) -> dict[str, Any]:
        if len(repo.list_goals(user_id, "active")) >= 20:
            raise HTTPException(422, "Trop d'objectifs actifs (20 maximum).")
        return repo.create_goal(user_id, {**body.model_dump(), "details": clean_details(body.details)})

    @router.patch("/{goal_id}")
    def edit_goal(goal_id: int, body: GoalPatch, user_id: int = Depends(require_user),
                  repo: Repo = Depends(get_repo)) -> dict[str, Any]:
        changes = body.model_dump(exclude_unset=True, exclude={"clear_date"})
        if changes.get("details") is not None:
            changes["details"] = clean_details(changes["details"])
        if body.clear_date:
            changes["target_date"] = None
        updated = repo.update_goal(user_id, goal_id, changes)
        if not updated:
            raise HTTPException(404, "Objectif inconnu.")
        return updated

    @router.delete("/{goal_id}")
    def delete_goal(goal_id: int, user_id: int = Depends(require_user),
                    repo: Repo = Depends(get_repo)) -> dict[str, bool]:
        if not repo.delete_goal(user_id, goal_id):
            raise HTTPException(404, "Objectif inconnu.")
        return {"ok": True}

    return router
