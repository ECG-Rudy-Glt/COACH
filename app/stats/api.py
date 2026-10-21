"""Écran « Statistiques » : tout est calculé ici à partir des données stockées, jamais par un LLM (règle ST1)."""
from datetime import date, timedelta
from typing import Any

from fastapi import APIRouter, Depends, Request
from pydantic import BaseModel

from app.nutrition import engine as eng
from app.nutrition.api import _day_load, _profile
from app.plan import trajectory
from app.plan.level import with_estimates
from app.questionnaire.models import Fact, current_facts
from app.repo import Repo
from app.stats import daily, progress, regularity

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


CURVE_WEEKS = 16  # courbes par exercice : quatre mois de séances
HISTORY_DAYS = 730


def progress_view(repo: Repo, user_id: int, today: date, catalog: dict[str, Any]) -> dict[str, Any]:
    facts = {k: v for k, v in current_facts(repo.list_facts(user_id)).items() if v is not None}
    goals = repo.list_goals(user_id, None)
    since = today - timedelta(days=HISTORY_DAYS)
    sessions = repo.list_sessions(user_id, since, today + timedelta(days=1))
    activities = repo.list_activities(user_id, since, 5000)
    metrics = [m for name in ("race_5k", "race_10k", "race_half") for m in repo.list_metrics(user_id, name, today - timedelta(days=365))]
    return {
        "today": today.isoformat(),
        "records": {"running": progress.run_records(facts, activities, metrics), "lifts": progress.lift_records(sessions), "declared_lifts": progress.declared_lifts(facts, catalog)},
        "trajectory": progress.trajectory_block(goals, with_estimates(facts, activities, sessions, goals, today), metrics, today),
        "curves": progress.exercise_curves(sessions, today - timedelta(weeks=CURVE_WEEKS)),
        "volume": {"weeks": progress.weekly_volume(sessions, activities, today), "weekly_km_target": _weekly_km_target(goals, today)},
        "pace": progress.pace_outings(activities, today),
    }


def _weekly_km_target(goals: list[dict[str, Any]], today: date) -> int | None:
    target = trajectory.pick_target(goals, today)
    return trajectory.volume_target_km(target["time_min"], target["distance_km"]) if target else None


PREF_FACTS = {"regularity": "ui.stats_regularity"}  # préférences d'affichage : un fait « manual » par clé, sans migration (ST13)


class Prefs(BaseModel):
    regularity: bool


def read_prefs(repo: Repo, user_id: int) -> dict[str, bool]:
    facts = current_facts(repo.list_facts(user_id))
    return {name: facts.get(key) is not False for name, key in PREF_FACTS.items()}  # activé tant que l'utilisateur ne l'a pas désactivé


def regularity_view(repo: Repo, user_id: int, today: date) -> dict[str, Any]:
    if not read_prefs(repo, user_id)["regularity"]:
        return {"enabled": False}  # désactivé : rien n'est calculé
    return regularity.regularity_view(repo.list_sessions(user_id, today - timedelta(weeks=regularity.HISTORY_WEEKS), today + timedelta(days=7)), today)


def build_router(get_repo: Any, require_user: Any) -> APIRouter:
    router = APIRouter(prefix="/users/{user_id}/stats", tags=["stats"])

    @router.get("/daily")
    def daily_stats(user_id: int = Depends(require_user), repo: Repo = Depends(get_repo)) -> dict[str, Any]:
        return daily_view(repo, user_id, date.today())

    @router.get("/progress")
    def progress_stats(request: Request, user_id: int = Depends(require_user), repo: Repo = Depends(get_repo)) -> dict[str, Any]:
        return progress_view(repo, user_id, date.today(), request.app.state.bench_index)

    @router.get("/regularity")
    def regularity_stats(user_id: int = Depends(require_user), repo: Repo = Depends(get_repo)) -> dict[str, Any]:
        return regularity_view(repo, user_id, date.today())

    @router.get("/preferences")
    def get_prefs(user_id: int = Depends(require_user), repo: Repo = Depends(get_repo)) -> dict[str, bool]:
        return read_prefs(repo, user_id)

    @router.put("/preferences")
    def set_prefs(body: Prefs, user_id: int = Depends(require_user), repo: Repo = Depends(get_repo)) -> dict[str, bool]:
        repo.add_facts(user_id, [Fact(key=PREF_FACTS[name], value=value, source="manual") for name, value in body.model_dump().items()])
        return read_prefs(repo, user_id)

    return router
