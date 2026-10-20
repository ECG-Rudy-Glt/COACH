"""API du coach : bilan, propositions à appliquer ou ignorer, budget."""
import os
from datetime import UTC, datetime, timedelta
from typing import Any

from fastapi import APIRouter, Depends, HTTPException, Request
from pydantic import BaseModel, Field

from app.coach import chat as chat_service
from app.coach import intake, notify, service
from app.coach.llm import is_configured
from app.config import env
from app.repo import Repo


class Prefs(BaseModel):
    ntfy_topic: str | None = Field(default=None, max_length=300)
    email: str | None = Field(default=None, max_length=300)
    push_enabled: bool = False
    email_enabled: bool = False


class Keys(BaseModel):
    p256dh: str = Field(min_length=10, max_length=200)
    auth: str = Field(min_length=6, max_length=100)


class Subscription(BaseModel):
    endpoint: str = Field(min_length=20, max_length=1000, pattern=r"^https://")
    keys: Keys


class Endpoint(BaseModel):
    endpoint: str = Field(max_length=1000)


class Say(BaseModel):
    message: str = Field(max_length=1500)


class Intake(BaseModel):
    force: bool = False  # refaire l'analyse même si elle existe (au plus 3 fois par jour)


class Clarification(BaseModel):
    index: int = Field(ge=0, le=5)
    answer: str = Field(min_length=1, max_length=600)


def _out(m: dict[str, Any] | None) -> dict[str, Any] | None:
    if not m:
        return None
    return {"id": m["id"], "summary": m["body"], "created_at": m["created_at"].isoformat(), "data": m["data"]}


def build_router(get_repo: Any, require_user: Any) -> APIRouter:
    router = APIRouter(prefix="/users/{user_id}/coach", tags=["coach"])

    @router.get("")
    def state(request: Request, user_id: int = Depends(require_user), repo: Repo = Depends(get_repo)) -> dict[str, Any]:
        latest = repo.list_memory(user_id, "weekly_review", 1)
        return {"configured": is_configured(request.app.state.llm), "budget": service.budget_state(repo),
                "latest": _out(latest[0] if latest else None)}

    @router.post("/review")
    def review(request: Request, user_id: int = Depends(require_user), repo: Repo = Depends(get_repo)) -> dict[str, Any]:
        return _out(service.review(repo, request.app.state.llm, user_id))  # type: ignore[return-value]

    @router.post("/intake")
    def intake_analyze(request: Request, body: Intake | None = None, user_id: int = Depends(require_user), repo: Repo = Depends(get_repo)) -> dict[str, Any]:
        """Après les questions essentielles : le coach dit s'il manque des informations (questions de la banque ou précisions libres), sinon « prêt »."""
        force = bool(body and body.force)
        if force and repo.llm_calls_since(user_id, intake.KIND, datetime.now(UTC) - timedelta(days=1)) >= 3:
            raise HTTPException(429, "Analyse déjà refaite plusieurs fois aujourd'hui.")
        return intake.analyze(repo, request.app.state.llm, request.app.state.bank, user_id, force=force)

    @router.post("/intake/clarification", status_code=201)
    def intake_clarification(body: Clarification, request: Request, user_id: int = Depends(require_user), repo: Repo = Depends(get_repo)) -> dict[str, Any]:
        try:
            intake.answer_clarification(repo, user_id, body.index, body.answer)
        except IndexError as e:
            raise HTTPException(404, "Précision inconnue.") from e
        return intake.render(request.app.state.bank, repo.list_facts(user_id), repo.list_memory(user_id, intake.KIND, 1)[0])

    @router.get("/chat")
    def chat_thread(request: Request, user_id: int = Depends(require_user), repo: Repo = Depends(get_repo)) -> dict[str, Any]:
        return {"messages": chat_service.thread(repo, user_id), "configured": is_configured(request.app.state.llm),
                "budget": service.budget_state(repo)}

    @router.post("/chat")
    def chat_say(body: Say, request: Request, user_id: int = Depends(require_user), repo: Repo = Depends(get_repo)) -> dict[str, Any]:
        return {"messages": chat_service.chat(repo, request.app.state.llm, user_id, body.message)}

    def prefs_out(repo: Repo, user_id: int, request: Request) -> dict[str, Any]:
        p = repo.get_prefs(user_id)
        return {"ntfy_topic": p["ntfy_topic"], "email": p["email"], "push_enabled": p["push_enabled"], "email_enabled": p["email_enabled"],
                "devices": len(repo.list_subscriptions(user_id)), "server": request.app.state.notifier.available(), "ntfy_url": os.environ.get("NTFY_PUBLIC_URL") or os.environ.get("NTFY_URL", "")}

    @router.get("/notifications")
    def get_prefs(request: Request, user_id: int = Depends(require_user), repo: Repo = Depends(get_repo)) -> dict[str, Any]:
        return prefs_out(repo, user_id, request)

    @router.put("/notifications")
    def put_prefs(body: Prefs, request: Request, user_id: int = Depends(require_user), repo: Repo = Depends(get_repo)) -> dict[str, Any]:
        topic = (body.ntfy_topic or "").strip() or None
        email = (body.email or "").strip() or None
        if topic and not notify.TOPIC_RE.match(topic):
            raise HTTPException(422, "Le sujet ntfy doit faire 8 à 64 caractères, uniquement des lettres, chiffres, - et _ (ni espace, ni point). Exemple : coach-" + "x" * 12)
        if email and not notify.EMAIL_RE.match(email):
            raise HTTPException(422, "Adresse mail invalide.")
        if body.push_enabled and not topic and not repo.list_subscriptions(user_id):
            raise HTTPException(422, "Activez d'abord les notifications sur cet appareil (ou renseignez un sujet ntfy).")
        if body.email_enabled and not email:
            raise HTTPException(422, "Renseignez l'adresse mail avant d'activer le mail.")
        repo.set_prefs(user_id, {"ntfy_topic": topic, "email": email, "push_enabled": body.push_enabled, "email_enabled": body.email_enabled})
        return prefs_out(repo, user_id, request)

    @router.post("/notifications/test/{channel}")
    def test_send(channel: str, request: Request, user_id: int = Depends(require_user), repo: Repo = Depends(get_repo)) -> dict[str, bool]:
        p, n = repo.get_prefs(user_id), request.app.state.notifier
        try:
            if channel == "push":
                notify.send_push(repo, n, user_id, "Sport Coach", "Test : vous recevrez ici les alertes de votre coach.", p)
            elif channel == "email" and p["email"]:
                n.email(p["email"], "Sport Coach : test", "Test : vous recevrez ici les conseils de votre coach.")
            else:
                raise HTTPException(422, "Canal inconnu ou non renseigné.")
        except notify.NotifyError as e:
            raise HTTPException(502, str(e)) from e
        return {"sent": True}

    @router.get("/push/key")
    def push_key(user_id: int = Depends(require_user)) -> dict[str, str | None]:
        return {"key": env("VAPID_PUBLIC_KEY") or None}

    @router.post("/push/subscribe")
    def push_subscribe(body: Subscription, user_id: int = Depends(require_user), repo: Repo = Depends(get_repo)) -> dict[str, int]:
        repo.add_subscription(user_id, body.endpoint, body.keys.p256dh, body.keys.auth)
        repo.set_prefs(user_id, {"push_enabled": True})
        return {"devices": len(repo.list_subscriptions(user_id))}

    @router.post("/push/unsubscribe")
    def push_unsubscribe(body: Endpoint, user_id: int = Depends(require_user), repo: Repo = Depends(get_repo)) -> dict[str, int]:
        repo.delete_subscription(user_id, body.endpoint)
        return {"devices": len(repo.list_subscriptions(user_id))}

    @router.post("/proposals/{memory_id}/{index}/apply")
    def apply(memory_id: int, index: int, user_id: int = Depends(require_user), repo: Repo = Depends(get_repo)) -> dict[str, Any]:
        return service.apply_proposal(repo, user_id, memory_id, index, dismiss=False)

    @router.post("/proposals/{memory_id}/{index}/dismiss")
    def dismiss(memory_id: int, index: int, user_id: int = Depends(require_user), repo: Repo = Depends(get_repo)) -> dict[str, Any]:
        return service.apply_proposal(repo, user_id, memory_id, index, dismiss=True)

    return router
