import logging
import os
from pathlib import Path

from fastapi import Depends, FastAPI, HTTPException, Request
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel

from app import evidence as evidence_mod
from app.auth import build_router as build_auth_router
from app.benchmarks import Benchmark, load_catalog, to_fact, visible_sections
from app.coach import notify as coach_notify
from app.coach.api import build_router as build_coach_router
from app.coach.llm import describe, is_configured, make_llm
from app.config import VERSION, load_settings
from app.exercises.api import build_router as build_exercises_router
from app.garmin import scheduler as garmin_scheduler
from app.garmin.api import build_router as build_garmin_router
from app.garmin.api import default_gateway
from app.goals import build_router as build_goals_router
from app.nutrition.api import build_router as build_nutrition_router
from app.plan.api import build_router as build_plan_router
from app.questionnaire.answers import AnswerError, to_facts
from app.questionnaire.bank import load_bank, validate_bank
from app.questionnaire.engine import next_questions, progress
from app.questionnaire.models import Fact, Question, current_facts
from app.repo import MemoryRepo, PostgresRepo, Repo

logging.basicConfig(level=logging.INFO, format="%(levelname)s %(name)s: %(message)s")
ROOT = Path(__file__).resolve().parent.parent


def build_state() -> tuple[list[Question], Repo]:
    bank = load_bank(Path(os.environ.get("QUESTIONS_DIR", ROOT / "questions")))
    problems = validate_bank(bank)
    if problems:
        raise RuntimeError("banque de questions invalide : " + "; ".join(problems))
    dsn = load_settings().database_url
    if dsn:
        repo = PostgresRepo(dsn)
        repo.migrate(Path(os.environ.get("MIGRATIONS_DIR", ROOT / "db" / "migrations")))
        return bank, repo
    return bank, MemoryRepo()


_docs = os.environ.get("ENABLE_DOCS", "") == "1"  # Swagger/OpenAPI : désactivés par défaut (surface inutile en production)
app = FastAPI(title="COACH", version=VERSION, docs_url="/docs" if _docs else None, redoc_url=None, openapi_url="/openapi.json" if _docs else None)
if os.environ.get("ALLOWED_HOSTS", "").strip():  # ex. « coach.example.org,localhost » : refuse tout autre en-tête Host
    from starlette.middleware.trustedhost import TrustedHostMiddleware

    app.add_middleware(TrustedHostMiddleware, allowed_hosts=[h.strip() for h in os.environ["ALLOWED_HOSTS"].split(",") if h.strip()])
app.state.bank, app.state.repo = build_state()
app.state.bench_sections, app.state.bench_index = load_catalog(
    Path(os.environ.get("QUESTIONS_DIR", ROOT / "questions")) / "benchmarks.yaml"
)


def get_repo(request: Request) -> Repo:
    return request.app.state.repo


def get_bank(request: Request) -> list[Question]:
    return request.app.state.bank


auth_router, current_user = build_auth_router(get_repo)
app.include_router(auth_router)
app.include_router(build_exercises_router(get_repo, current_user))
app.state.evidence = evidence_mod.load_evidence(ROOT / "data" / "evidence", set(__import__("yaml").safe_load((ROOT / "data" / "rules_digest.yaml").read_text(encoding="utf-8"))))
app.include_router(evidence_mod.build_router(current_user))
from app.coach import service as _coach_service  # noqa: E402

_by_rule: dict[str, list[str]] = {}
for _e in app.state.evidence:
    for _r in _e["applies_to"]:
        _by_rule.setdefault(_r, []).append(_e["id"])  # liste déjà triée : preuves solides d'abord
_coach_service.set_evidence(evidence_mod.digest(app.state.evidence), {e["id"] for e in app.state.evidence}, _by_rule)


@app.middleware("http")
async def revalidate_static(request: Request, call_next):
    """L'interface (HTML, JS, CSS) est revalidée à chaque ouverture : un déploiement n'est jamais masqué par un cache de l'appareil."""
    response = await call_next(request)
    p = request.url.path
    if request.method == "GET" and not p.startswith(("/users", "/auth", "/media", "/exercises", "/evidence", "/bank", "/fonts", "/icons")):
        response.headers["Cache-Control"] = "no-cache"
    return response


CSP = ("default-src 'self'; script-src 'self'; style-src 'self' 'unsafe-inline'; img-src 'self' data: blob:; media-src 'self'; "
       "connect-src 'self'; font-src 'self'; manifest-src 'self'; worker-src 'self'; object-src 'none'; base-uri 'none'; "
       "form-action 'self'; frame-ancestors 'none'")


@app.middleware("http")
async def security_headers(request: Request, call_next):
    """En-têtes de défense en profondeur sur chaque réponse (CSP sans script en ligne, pas d'inclusion en cadre, HSTS en HTTPS)."""
    response = await call_next(request)
    h = response.headers
    h.setdefault("Content-Security-Policy", CSP)
    h.setdefault("X-Content-Type-Options", "nosniff")
    h.setdefault("X-Frame-Options", "DENY")
    h.setdefault("Referrer-Policy", "same-origin")
    h.setdefault("Permissions-Policy", "camera=(), microphone=(), geolocation=(), payment=(), usb=()")
    h.setdefault("Cross-Origin-Opener-Policy", "same-origin")
    if request.url.scheme == "https" or request.headers.get("x-forwarded-proto") == "https":
        h.setdefault("Strict-Transport-Security", "max-age=31536000")
    return response


@app.middleware("http")
async def same_origin_writes(request: Request, call_next):
    """Les écritures venant d'une autre origine sont refusées (complète le cookie SameSite=Lax)."""
    origin = request.headers.get("origin")
    if request.method in ("POST", "PUT", "PATCH", "DELETE") and origin:
        host = request.headers.get("host", "")
        if origin.split("://", 1)[-1] != host:
            from fastapi.responses import JSONResponse
            return JSONResponse({"detail": "Origine refusée."}, status_code=403)
    return await call_next(request)


def require_user(user_id: int, me: dict = Depends(current_user)) -> int:
    """L'utilisateur connecté ne peut accéder qu'à ses propres données."""
    if me["id"] != user_id:
        raise HTTPException(403, "Accès refusé.")
    return user_id


class BenchmarkBatch(BaseModel):
    items: dict[str, dict]


class Skip(BaseModel):
    question_id: str


class Answer(BaseModel):
    question_id: str
    value: object
    other_text: str | None = None


@app.get("/healthz")
def healthz() -> dict[str, str]:
    """Sonde de vivacité (Docker, Kubernetes) : ne dépend d'aucun service externe."""
    return {"status": "ok"}


@app.get("/version")
def version(repo: Repo = Depends(get_repo)) -> dict[str, str]:
    return {"version": VERSION, "llm_provider": load_settings().llm_provider, "storage": repo.name}


@app.get("/llm")
def llm_info(_: int = Depends(current_user)) -> dict:
    """Fournisseur et modèle d'IA actifs, liste des modèles suggérés (jamais de clé) ; `configured` = prêt à répondre."""
    return {**describe(), "configured": is_configured(app.state.llm)}


app.include_router(build_goals_router(get_repo, require_user))
app.include_router(build_plan_router(get_repo, require_user))
app.include_router(build_nutrition_router(get_repo, require_user))
app.state.garmin = default_gateway()
app.include_router(build_garmin_router(get_repo, require_user))
app.state.llm = make_llm()
app.state.notifier = coach_notify.Notifier()
app.include_router(build_coach_router(get_repo, require_user))


@app.on_event("startup")
def _start_background() -> None:
    garmin_scheduler.start(app.state.repo, app.state.garmin)  # actif seulement si AUTO_SYNC=1
    coach_notify.start(app.state.repo, app.state.llm, app.state.notifier)  # actif seulement si AUTO_NOTIFY=1


@app.get("/bank")
def get_questions(bank: list[Question] = Depends(get_bank)) -> list[dict]:
    """Questions publiques (sans les conditions) pour afficher libellés et profil."""
    return [q.model_dump(exclude={"show_if"}) for q in bank]


@app.get("/users/{user_id}/questions/next")
def questions_next(
    n: int = 1,
    domain: str | None = None,
    user_id: int = Depends(require_user),
    repo: Repo = Depends(get_repo),
    bank: list[Question] = Depends(get_bank),
) -> dict:
    n = max(1, min(n, 10))
    facts = repo.list_facts(user_id)
    return {
        "questions": [q.model_dump(exclude={"show_if", "fact_key"}) for q in
                      next_questions(bank, facts, n, domain)],
        **progress(bank, facts),
    }


@app.post("/users/{user_id}/answers", status_code=201)
def post_answer(
    body: Answer,
    user_id: int = Depends(require_user),
    repo: Repo = Depends(get_repo),
    bank: list[Question] = Depends(get_bank),
) -> dict:
    q = next((x for x in bank if x.id == body.question_id), None)
    if q is None:
        raise HTTPException(404, "question inconnue")
    try:
        facts = to_facts(q, body.value, body.other_text)
    except AnswerError as e:
        raise HTTPException(422, str(e)) from e
    repo.add_facts(user_id, facts)
    return {"recorded": [f.key for f in facts], **progress(bank, repo.list_facts(user_id))}


@app.post("/users/{user_id}/skip", status_code=201)
def skip_question(
    body: Skip,
    user_id: int = Depends(require_user),
    repo: Repo = Depends(get_repo),
    bank: list[Question] = Depends(get_bank),
) -> dict:
    q = next((x for x in bank if x.id == body.question_id), None)
    if q is None:
        raise HTTPException(404, "question inconnue")
    if q.blocking:
        raise HTTPException(422, "cette question ne peut pas être passée")
    repo.add_facts(user_id, [Fact(key=q.fact_key, value=None, source="skipped")])
    return progress(bank, repo.list_facts(user_id))


@app.get("/users/{user_id}/benchmarks")
def get_benchmarks(
    request: Request,
    user_id: int = Depends(require_user),
    repo: Repo = Depends(get_repo),
) -> dict:
    cur = current_facts(repo.list_facts(user_id))
    sports = cur.get("sports.practiced") or []
    sections = visible_sections(request.app.state.bench_sections, sports)
    values = {k.removeprefix("bench."): v for k, v in cur.items() if k.startswith("bench.") and v}
    filled = sum(1 for s in sections for it in s["items"] if it["id"] in values)
    total = sum(len(s["items"]) for s in sections)
    years = cur.get("history.sport_years")
    novice = isinstance(years, int | float) and years < 1 and not values  # débutant déclaré : pas de records à saisir, ses premières séances servent de référence
    return {"sections": sections, "values": values, "filled": filled, "total": total, "novice": bool(novice)}


@app.put("/users/{user_id}/benchmarks")
def put_benchmarks(
    body: BenchmarkBatch,
    request: Request,
    user_id: int = Depends(require_user),
    repo: Repo = Depends(get_repo),
) -> dict:
    index: dict[str, Benchmark] = request.app.state.bench_index
    facts = []
    for bid, payload in body.items.items():
        if bid not in index:
            raise HTTPException(404, f"exercice inconnu : {bid}")
        try:
            facts.append(to_fact(index[bid], payload))
        except AnswerError as e:
            raise HTTPException(422, str(e)) from e
    repo.add_facts(user_id, facts)
    return {"saved": len(facts)}


@app.get("/users/{user_id}/profile")
def profile(
    user_id: int = Depends(require_user),
    repo: Repo = Depends(get_repo),
    bank: list[Question] = Depends(get_bank),
) -> dict:
    facts = repo.list_facts(user_id)
    cur = {k: v for k, v in current_facts(facts).items()
           if v is not None and not k.startswith("bench.")}
    return {"facts": cur, **progress(bank, facts)}


# Doit rester en dernier : la PWA est servie à la racine, derrière les routes de l'API.
app.mount("/", StaticFiles(directory=ROOT / "app" / "static", html=True), name="static")
