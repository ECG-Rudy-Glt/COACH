"""Comptes locaux : mot de passe haché (scrypt), sessions en cookie HttpOnly, limitation des essais."""
import base64
import hashlib
import hmac
import os
import re
import secrets
import time
from datetime import UTC, datetime, timedelta
from typing import Any

from fastapi import APIRouter, Depends, HTTPException, Request, Response
from pydantic import BaseModel, Field

from app import i18n
from app.repo import Repo

COOKIE = "sc_session"
SESSION_DAYS = 30
MIN_PASSWORD = 10
EMAIL_RE = re.compile(r"^[^@\s]+@[^@\s]+\.[^@\s]+$")
_N, _R, _P = 2**15, 8, 1
_fails: dict[str, list[float]] = {}
MAX_FAILS, WINDOW = 5, 15 * 60
MAX_FAILS_PER_ACCOUNT = 20  # toutes adresses confondues : borne la force brute distribuée


def hash_password(password: str) -> str:
    salt = os.urandom(16)
    dk = hashlib.scrypt(password.encode(), salt=salt, n=_N, r=_R, p=_P, maxmem=64 * 1024 * 1024, dklen=32)
    b = base64.b64encode
    return f"scrypt${_N}${_R}${_P}${b(salt).decode()}${b(dk).decode()}"


def verify_password(password: str, stored: str) -> bool:
    try:
        _, n, r, p, salt, dk = stored.split("$")
        got = hashlib.scrypt(password.encode(), salt=base64.b64decode(salt), n=int(n), r=int(r), p=int(p),
                             maxmem=64 * 1024 * 1024, dklen=32)
        return hmac.compare_digest(got, base64.b64decode(dk))
    except (ValueError, TypeError):
        return False


def token_hash(token: str) -> str:
    return hashlib.sha256(token.encode()).hexdigest()


def _check_rate(key: str, limit: int = MAX_FAILS) -> None:
    now = time.time()
    recent = [t for t in _fails.get(key, []) if now - t < WINDOW]
    _fails[key] = recent
    if len(recent) >= limit:
        raise HTTPException(429, "Trop d'essais. Réessayez dans quelques minutes.")


def _fail(key: str) -> None:
    _fails.setdefault(key, []).append(time.time())


def reset_rate_limits() -> None:
    _fails.clear()


def _validate(name: str, email: str, password: str) -> tuple[str, str]:
    name, email = name.strip(), email.strip().lower()
    if not name or len(name) > 60:
        raise HTTPException(422, "Indiquez un prénom (60 caractères maximum).")
    if not EMAIL_RE.match(email) or len(email) > 200:
        raise HTTPException(422, "Adresse email invalide.")
    if len(password) < MIN_PASSWORD:
        raise HTTPException(422, f"Le mot de passe doit faire au moins {MIN_PASSWORD} caractères.")
    if len(password) > 128:
        raise HTTPException(422, "Mot de passe trop long (128 caractères maximum).")
    if password.lower() == email:
        raise HTTPException(422, "Le mot de passe ne doit pas être votre email.")
    return name, email


class Register(BaseModel):
    name: str
    email: str
    password: str
    adopt_user_id: int | None = None


class ChangePassword(BaseModel):
    current: str
    new: str


class Language(BaseModel):
    lang: str = Field(max_length=10)


class Login(BaseModel):
    email: str
    password: str


def _client_ip(request: Request) -> str:
    """IP réelle pour limiter les essais. `X-Forwarded-For` n'est lu que si `TRUST_PROXY=1` (application derrière un proxy ou un
    tunnel de confiance) : exposée directement, elle serait falsifiable. Le dernier saut, ajouté par notre proxy, fait foi."""
    if os.environ.get("TRUST_PROXY", "") == "1":
        fwd = request.headers.get("x-forwarded-for", "").split(",")[-1].strip()
        if fwd:
            return fwd
    return request.client.host if request.client else "?"


def _registration(repo: Repo) -> str:
    """`REGISTRATION` = open | closed | first (défaut : ouverte seulement tant qu'aucun compte n'existe, puis fermée)."""
    mode = os.environ.get("REGISTRATION", "first").strip().lower()
    if mode == "first":
        return "closed" if repo.has_accounts() else "open"
    return "open" if mode == "open" else "closed"


def _is_https(request: Request) -> bool:
    """HTTPS direct ou derrière Traefik (X-Forwarded-Proto). En HTTP pur, le cookie reste utilisable."""
    return request.url.scheme == "https" or request.headers.get("x-forwarded-proto", "") == "https"


def _set_cookie(response: Response, token: str, secure: bool) -> None:
    response.set_cookie(
        COOKIE, token, max_age=SESSION_DAYS * 86400, httponly=True, samesite="lax",
        secure=secure or os.environ.get("COOKIE_SECURE", "") == "1", path="/",
    )


def _open_session(repo: Repo, user_id: int, request: Request, response: Response) -> None:
    token = secrets.token_urlsafe(32)
    repo.create_session(user_id, token_hash(token), datetime.now(UTC) + timedelta(days=SESSION_DAYS))
    _set_cookie(response, token, _is_https(request))


def build_router(get_repo: Any) -> tuple[APIRouter, Any]:
    router = APIRouter(prefix="/auth", tags=["auth"])

    def current_user(request: Request, repo: Repo = Depends(get_repo)) -> dict[str, Any]:
        token = request.cookies.get(COOKIE)
        user = repo.get_session_user(token_hash(token)) if token else None
        if not user:
            raise HTTPException(401, "Connexion requise.")
        return user

    @router.get("/status")
    def status(repo: Repo = Depends(get_repo)) -> dict[str, Any]:
        """Public : indique si l'inscription est ouverte et quels profils anciens peuvent être repris."""
        mode = _registration(repo)
        legacy = repo.list_legacy_users() if mode == "open" else []
        return {"registration": mode, "legacy": legacy}

    @router.post("/register", status_code=201)
    def register(body: Register, request: Request, response: Response,
                 repo: Repo = Depends(get_repo)) -> dict[str, Any]:
        if _registration(repo) != "open":
            raise HTTPException(403, "Les inscriptions sont fermées.")
        name, email = _validate(body.name, body.email, body.password)
        if repo.get_account(email):
            raise HTTPException(409, "Un compte existe déjà avec cet email.")
        pw = hash_password(body.password)
        if body.adopt_user_id is not None:
            if not repo.adopt_legacy_user(body.adopt_user_id, name, email, pw):
                raise HTTPException(422, "Ce profil ne peut pas être repris.")
            uid = body.adopt_user_id
        else:
            uid = repo.create_account(name, email, pw)
        _open_session(repo, uid, request, response)
        return {"id": uid, "name": name, "email": email, "lang": None}

    @router.post("/login")
    def login(body: Login, request: Request, response: Response,
              repo: Repo = Depends(get_repo)) -> dict[str, Any]:
        email = body.email.strip().lower()
        key = f"{_client_ip(request)}|{email}"
        _check_rate(key)
        _check_rate(f"*|{email}", MAX_FAILS_PER_ACCOUNT)
        acct = repo.get_account(email)
        ok = verify_password(body.password, acct["password_hash"]) if acct else verify_password(
            body.password, "scrypt$32768$8$1$AAAAAAAAAAAAAAAAAAAAAA==$" + "A" * 43 + "=")
        if not acct or not ok:
            _fail(key)
            _fail(f"*|{email}")
            raise HTTPException(401, "Email ou mot de passe incorrect.")
        _fails.pop(key, None)
        _fails.pop(f"*|{email}", None)
        _open_session(repo, acct["id"], request, response)
        return {"id": acct["id"], "name": acct["name"], "email": email, "lang": acct.get("lang")}

    @router.post("/logout")
    def logout(request: Request, response: Response, repo: Repo = Depends(get_repo)) -> dict[str, bool]:
        token = request.cookies.get(COOKIE)
        if token:
            repo.delete_session(token_hash(token))
        response.delete_cookie(COOKIE, path="/")
        return {"ok": True}

    @router.post("/change-password")
    def change_password(body: ChangePassword, request: Request, user: dict[str, Any] = Depends(current_user),
                        repo: Repo = Depends(get_repo)) -> dict[str, bool]:
        key = f"pw|{user['id']}"
        _check_rate(key)
        acct = repo.get_account(user["email"])
        if not acct or not verify_password(body.current, acct["password_hash"]):
            _fail(key)
            raise HTTPException(401, "Mot de passe actuel incorrect.")
        _validate(user["name"], user["email"], body.new)
        if body.new == body.current:
            raise HTTPException(422, "Le nouveau mot de passe doit être différent.")
        repo.set_password(user["id"], hash_password(body.new), token_hash(request.cookies.get(COOKIE, "")))
        return {"ok": True}

    @router.put("/language")
    def set_language(body: Language, user: dict[str, Any] = Depends(current_user), repo: Repo = Depends(get_repo)) -> dict[str, str]:
        """Langue du compte : l'interface la mémorise sur l'appareil, le serveur s'en sert pour les notifications, les mails et le coach IA."""
        lang = i18n.normalize(body.lang)
        if lang is None:
            raise HTTPException(422, "Langue non gérée.")
        repo.set_language(user["id"], lang)
        return {"lang": lang}

    @router.get("/me")
    def me(user: dict[str, Any] = Depends(current_user)) -> dict[str, Any]:
        return user

    return router, current_user
