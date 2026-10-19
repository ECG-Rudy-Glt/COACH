"""API nutrition : cibles du jour, repas (texte, photo, estimation IA), poids et progression."""
import base64
import binascii
import os
import uuid
from datetime import UTC, date, datetime, timedelta
from pathlib import Path
from typing import Any, Literal

from fastapi import APIRouter, Depends, HTTPException, Request
from fastapi.responses import FileResponse
from pydantic import BaseModel, Field

from app.coach import service as coach
from app.coach.llm import LLMError, fast_model
from app.nutrition import analyze as nut_analyze
from app.nutrition import engine as eng
from app.questionnaire.models import current_facts
from app.repo import Repo

SLOTS = ("petit-déjeuner", "déjeuner", "dîner", "collation")
MAX_PHOTO = 3 * 1024 * 1024
MAX_MEALS_PER_DAY = 12
MAX_ESTIMATES_PER_DAY = 15
MAGIC = {b"\xff\xd8\xff": ("image/jpeg", "jpg"), b"\x89PNG": ("image/png", "png")}


def media_dir() -> Path:
    return Path(os.environ.get("MEDIA_DIR", "/tmp/sport-coach-media")) / "meals"


class MealIn(BaseModel):
    day: date | None = None
    slot: Literal["petit-déjeuner", "déjeuner", "dîner", "collation"]
    description: str = Field(default="", max_length=800)
    photo_b64: str | None = Field(default=None, max_length=5_000_000)
    estimate: bool = True


class WeightIn(BaseModel):
    day: date | None = None
    kg: float = Field(ge=30, le=250)
    waist_cm: float | None = Field(default=None, ge=40, le=200)


def _save_photo(user_id: int, b64: str) -> tuple[str, str, str]:
    """Valide l'image (octets magiques, taille) et l'enregistre ; retourne (chemin, type MIME, base64 nettoyé)."""
    try:
        raw = base64.b64decode(b64.split(",", 1)[-1], validate=True)
    except (binascii.Error, ValueError) as e:
        raise HTTPException(422, "Photo illisible.") from e
    if len(raw) > MAX_PHOTO:
        raise HTTPException(422, "Photo trop volumineuse (3 Mo maximum).")
    kind = next((v for k, v in MAGIC.items() if raw.startswith(k)), None)
    if not kind:
        raise HTTPException(422, "Format de photo non pris en charge (JPEG ou PNG).")
    d = media_dir() / str(user_id)
    d.mkdir(parents=True, exist_ok=True)
    path = d / f"{uuid.uuid4().hex}.{kind[1]}"
    path.write_bytes(raw)
    return str(path), kind[0], base64.b64encode(raw).decode()


def _public(m: dict[str, Any]) -> dict[str, Any]:
    return {"id": m["id"], "day": m["day"].isoformat(), "slot": m["slot"], "description": m["description"], "has_photo": bool(m["photo_path"]),
            "analysis": m["analysis"]}


def _profile(repo: Repo, user_id: int, today: date) -> tuple[eng.NutritionProfile, dict[str, Any]]:
    facts = {k: v for k, v in current_facts(repo.list_facts(user_id)).items() if v is not None}
    weights = repo.list_weights(user_id, today - timedelta(days=60))
    monday = today - timedelta(days=today.weekday())
    sessions = repo.list_sessions(user_id, monday, monday + timedelta(days=7))
    events = [g for g in repo.list_goals(user_id, "active") if g["kind"] == "event" and g.get("target_date") and g["target_date"] >= today]
    wte = min(((g["target_date"] - today).days // 7 for g in events), default=None)
    return eng.build_profile(facts, today, weights[-1]["kg"] if weights else None, sessions, wte), facts


def _day_load(repo: Repo, user_id: int, day: date) -> str:
    s = repo.list_sessions(user_id, day, day + timedelta(days=1))
    return "training" if any(x["duration_min"] >= 45 and x["status"] != "skipped" for x in s) else "rest"


def _sum(meals: list[dict[str, Any]]) -> dict[str, Any]:
    done = [m["analysis"] for m in meals if m["analysis"]]
    return {"kcal": sum(a["kcal"] for a in done), "protein_g": sum(a["protein_g"] for a in done), "carbs_g": sum(a["carbs_g"] for a in done),
            "fat_g": sum(a["fat_g"] for a in done), "estimated_meals": len(done), "meals": len(meals)}


def _estimate(repo: Repo, llm: Any, user_id: int, meal: dict[str, Any]) -> dict[str, Any]:
    if not coach.budget_state(repo)["available"]:
        raise HTTPException(429, "Le plafond mensuel d'utilisation de l'IA est atteint.")
    since = datetime.now(UTC) - timedelta(days=1)
    if repo.llm_calls_since(user_id, "meal", since) >= MAX_ESTIMATES_PER_DAY:
        raise HTTPException(429, "Trop d'estimations aujourd'hui. Réessayez demain.")
    image = None
    if meal["photo_path"] and Path(meal["photo_path"]).exists():
        raw = Path(meal["photo_path"]).read_bytes()
        mime = "image/png" if raw.startswith(b"\x89PNG") else "image/jpeg"
        image = (mime, base64.b64encode(raw).decode())
    model = fast_model()
    try:
        analysis, usage = nut_analyze.analyze(llm, meal["description"], image, model)
    except LLMError as e:
        repo.log_llm_call(user_id, "meal", model, (0, 0), 0.0, False, str(e)[:200])
        raise HTTPException(502, str(e)) from e
    except ValueError as e:
        raise HTTPException(502, "L'estimation n'a pas pu être lue. Réessayez.") from e
    repo.log_llm_call(user_id, "meal", usage["model"], (usage["in"], usage["out"]), usage["cost"], True, None)
    repo.set_meal_analysis(user_id, meal["id"], analysis)
    return analysis


def week_summary(repo: Repo, user_id: int, today: date) -> dict[str, Any]:
    """Résumé des 7 derniers jours pour le mail et le coach : repas saisis, moyennes estimées, tendance de poids."""
    p, _ = _profile(repo, user_id, today)
    tg = eng.targets(p)
    meals = repo.list_meals(user_id, today - timedelta(days=6), today)
    est: dict[date, list[dict[str, Any]]] = {}
    for m in meals:
        if m["analysis"]:
            est.setdefault(m["day"], []).append(m["analysis"])
    n = len(est)
    tr = eng.trend(repo.list_weights(user_id, today - timedelta(days=60)), today)
    return {"jours_avec_repas": len({m["day"] for m in meals}), "jours_estimes": n,
            "kcal_moyennes": round(sum(a["kcal"] for v in est.values() for a in v) / n) if n else None,
            "proteines_moyennes_g": round(sum(a["protein_g"] for v in est.values() for a in v) / n) if n else None,
            "cible_kcal": tg["kcal"], "cible_proteines_g": tg["protein_g"], "poids_tendance_kg": tr.get("current"),
            "rythme_pct_par_semaine": tr.get("rate_pct_per_week"), "objectif_kg": p.target_kg,
            "avertissement": "estimations de repas souvent sous-évaluées : on suit la tendance, pas un jour isolé"}


def build_router(get_repo: Any, require_user: Any) -> APIRouter:
    router = APIRouter(prefix="/users/{user_id}/nutrition", tags=["nutrition"])

    @router.get("/day")
    def day_view(day: date | None = None, user_id: int = Depends(require_user), repo: Repo = Depends(get_repo)) -> dict[str, Any]:
        today = date.today()
        d = day or today
        p, _ = _profile(repo, user_id, today)
        tg = eng.targets(p, _day_load(repo, user_id, d))
        meals = repo.list_meals(user_id, d, d)
        tot = _sum(meals)
        rem = {k: max(tg[k] - tot[k], 0) for k in ("kcal", "protein_g", "carbs_g", "fat_g")}
        return {"day": d.isoformat(), "today": today.isoformat(), "targets": tg, "meals": [_public(m) for m in meals], "totals": tot, "remaining": rem}

    @router.post("/meals", status_code=201)
    def add_meal(body: MealIn, request: Request, user_id: int = Depends(require_user), repo: Repo = Depends(get_repo)) -> dict[str, Any]:
        today = date.today()
        d = body.day or today
        if d > today + timedelta(days=1) or d < today - timedelta(days=14):
            raise HTTPException(422, "Date hors de la plage autorisée (14 jours passés).")
        if not body.description.strip() and not body.photo_b64:
            raise HTTPException(422, "Décrivez votre repas ou ajoutez une photo.")
        if len(repo.list_meals(user_id, d, d)) >= MAX_MEALS_PER_DAY:
            raise HTTPException(422, "Trop de repas pour cette journée.")
        path = None
        if body.photo_b64:
            path, _, _ = _save_photo(user_id, body.photo_b64)
        meal = repo.add_meal(user_id, d, body.slot, body.description.strip(), path)
        out: dict[str, Any] = {"meal": _public(meal), "analysis_error": None}
        if body.estimate:
            try:
                _estimate(repo, request.app.state.llm, user_id, meal)
            except HTTPException as e:  # le repas reste enregistré même si l'estimation échoue
                out["analysis_error"] = e.detail
            out["meal"] = _public(repo.get_meal(user_id, meal["id"]))  # type: ignore[arg-type]
        return out

    @router.post("/meals/{meal_id}/estimate")
    def estimate(meal_id: int, request: Request, user_id: int = Depends(require_user), repo: Repo = Depends(get_repo)) -> dict[str, Any]:
        meal = repo.get_meal(user_id, meal_id)
        if not meal:
            raise HTTPException(404, "Repas inconnu.")
        _estimate(repo, request.app.state.llm, user_id, meal)
        return _public(repo.get_meal(user_id, meal_id))  # type: ignore[arg-type]

    @router.delete("/meals/{meal_id}")
    def delete_meal(meal_id: int, user_id: int = Depends(require_user), repo: Repo = Depends(get_repo)) -> dict[str, bool]:
        path = repo.delete_meal(user_id, meal_id)
        if path is None:
            raise HTTPException(404, "Repas inconnu.")
        if path:
            Path(path).unlink(missing_ok=True)
        return {"ok": True}

    @router.get("/meals/{meal_id}/photo")
    def photo(meal_id: int, user_id: int = Depends(require_user), repo: Repo = Depends(get_repo)) -> FileResponse:
        m = repo.get_meal(user_id, meal_id)
        if not m or not m["photo_path"] or not Path(m["photo_path"]).exists():
            raise HTTPException(404, "Photo introuvable.")
        mime = "image/png" if m["photo_path"].endswith(".png") else "image/jpeg"
        return FileResponse(m["photo_path"], media_type=mime, headers={"Cache-Control": "private, max-age=86400"})

    @router.post("/weight")
    def weight(body: WeightIn, user_id: int = Depends(require_user), repo: Repo = Depends(get_repo)) -> dict[str, Any]:
        today = date.today()
        d = body.day or today
        if d > today or d < today - timedelta(days=120):
            raise HTTPException(422, "Date hors de la plage autorisée.")
        repo.upsert_weight(user_id, d, body.kg, body.waist_cm)
        return {"ok": True, "day": d.isoformat()}

    @router.get("/progress")
    def progress(user_id: int = Depends(require_user), repo: Repo = Depends(get_repo)) -> dict[str, Any]:
        today = date.today()
        p, facts = _profile(repo, user_id, today)
        tg = eng.targets(p)
        weights = repo.list_weights(user_id, today - timedelta(days=120))
        tr = eng.trend(weights, today)
        meals = repo.list_meals(user_id, today - timedelta(days=13), today)
        days_logged = len({m["day"] for m in meals})
        week = [m for m in meals if m["day"] > today - timedelta(days=7)]
        wdays = {m["day"] for m in week if m["analysis"]}
        avg = None
        if wdays:
            s = _sum([m for m in week if m["analysis"]])
            avg = {"kcal": round(s["kcal"] / len(wdays)), "protein_g": round(s["protein_g"] / len(wdays)), "days": len(wdays)}
        bmi = round(p.weight_kg / (p.height_cm / 100) ** 2, 1)
        return {"profile": {"height_cm": p.height_cm, "weight_kg": p.weight_kg, "target_kg": p.target_kg, "bmi": bmi, "direction": p.direction},
                "targets": tg, "trend": tr, "weights": [{"day": w["day"].isoformat(), "kg": w["kg"], "waist_cm": w["waist_cm"]} for w in weights][-30:],
                "week_average": avg, "days_logged_14": days_logged, "advice": eng.advice(p, tg, tr, days_logged),
                "disclaimer": "Estimations : ce suivi ne remplace pas un avis médical ou diététique."}

    return router
