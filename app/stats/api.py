"""Écran « Statistiques » : tout est calculé ici à partir des données stockées, jamais par un LLM (règle ST1)."""
from datetime import date, timedelta
from typing import Any

from fastapi import APIRouter, Depends

from app.nutrition import engine as eng
from app.nutrition.api import _day_load, _profile
from app.repo import Repo
from app.stats import daily

PROFILE_FACTS = ("body.height_cm", "body.birth_year")  # sans eux, la cible énergétique serait celle d'un profil par défaut : on ne l'affiche pas (ST1)


def daily_view(repo: Repo, user_id: int, today: date) -> dict[str, Any]:
    p, facts = _profile(repo, user_id, today)
    weights = repo.list_weights(user_id, today - timedelta(days=60))
    has_weight = bool(weights) or bool(facts.get("body.weight_kg"))
    targets = None
    if all(facts.get(k) for k in PROFILE_FACTS) and has_weight:
        targets = {d: eng.targets(p, _day_load(repo, user_id, d)) for d in daily.last_days(today)}
    since = today - timedelta(days=13)
    activities = repo.list_activities(user_id, since, 200)
    sessions = repo.list_sessions(user_id, since, today + timedelta(days=7))
    connected = repo.get_garmin(user_id) is not None
    return {
        "today": today.isoformat(),
        "steps": daily.steps_block(repo.list_metrics(user_id, "steps", today - timedelta(days=7)), today, connected),
        "nutrition": daily.nutrition_block(repo.list_meals(user_id, today - timedelta(days=6), today), today, targets),
        "weight": daily.weight_block(eng.trend(weights, today), p.target_kg),
        "week": daily.week_block(sessions, activities, today),
        "recent": daily.recent_items(activities, sessions, today),
    }


def build_router(get_repo: Any, require_user: Any) -> APIRouter:
    router = APIRouter(prefix="/users/{user_id}/stats", tags=["stats"])

    @router.get("/daily")
    def daily_stats(user_id: int = Depends(require_user), repo: Repo = Depends(get_repo)) -> dict[str, Any]:
        return daily_view(repo, user_id, date.today())

    return router
