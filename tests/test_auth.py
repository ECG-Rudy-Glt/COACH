import pytest
from fastapi.testclient import TestClient

from app.auth import hash_password, reset_rate_limits, verify_password
from app.main import app, get_repo
from app.questionnaire.models import Fact
from app.repo import MemoryRepo

PW = "un-mot-de-passe-solide"


@pytest.fixture
def ctx():
    reset_rate_limits()
    repo = MemoryRepo()
    app.dependency_overrides[get_repo] = lambda: repo
    yield TestClient(app), repo
    app.dependency_overrides.clear()


def reg(c, email="a@example.org", pw=PW, **kw):
    return c.post("/auth/register", json={"name": "Rudy", "email": email, "password": pw, **kw})


def test_hash_roundtrip_and_unique_salt():
    h = hash_password("secret-assez-long")
    assert verify_password("secret-assez-long", h) and not verify_password("autre", h)
    assert h != hash_password("secret-assez-long") and "secret" not in h
    assert not verify_password("x", "format-invalide")


def test_register_login_logout_me(ctx):
    c, _ = ctx
    r = reg(c)
    assert r.status_code == 201 and "sc_session" in r.cookies
    assert "httponly" in r.headers["set-cookie"].lower() and "samesite=lax" in r.headers["set-cookie"].lower()
    assert c.get("/auth/me").json()["email"] == "a@example.org"
    c.post("/auth/logout")
    assert c.get("/auth/me").status_code == 401
    r = c.post("/auth/login", json={"email": "A@Example.org", "password": PW})
    assert r.status_code == 200 and c.get("/auth/me").status_code == 200


def test_register_validation(ctx):
    c, _ = ctx
    assert reg(c, pw="court").status_code == 422
    assert reg(c, email="pas-un-email").status_code == 422
    assert reg(c).status_code == 201
    assert reg(c).status_code == 409


def test_login_errors_are_generic_and_rate_limited(ctx):
    c, _ = ctx
    reg(c)
    c.post("/auth/logout")
    msgs = {c.post("/auth/login", json={"email": e, "password": "mauvais-mdp-long"}).json()["detail"]
            for e in ("a@example.org", "inconnu@example.org")}
    assert len(msgs) == 1  # même message : pas de fuite sur l'existence du compte
    for _ in range(4):
        c.post("/auth/login", json={"email": "a@example.org", "password": "mauvais-mdp-long"})
    assert c.post("/auth/login", json={"email": "a@example.org", "password": PW}).status_code == 429


def test_adopt_legacy_profile(ctx):
    c, repo = ctx
    old = repo.create_user("Rudy")
    repo.add_facts(old, [Fact(key="body.weight_kg", value=78)])
    status = c.get("/auth/status").json()
    assert status["legacy"] == [{"id": old, "name": "Rudy", "answers": 1}]
    r = reg(c, adopt_user_id=old)
    assert r.status_code == 201 and r.json()["id"] == old
    assert c.get(f"/users/{old}/profile").json()["facts"]["body.weight_kg"] == 78
    # un profil déjà repris ne peut plus l'être
    c.post("/auth/logout")
    assert reg(c, email="b@example.org", adopt_user_id=old).status_code == 422


def test_registration_can_be_closed(ctx, monkeypatch):
    c, _ = ctx
    monkeypatch.setenv("REGISTRATION", "closed")
    assert reg(c).status_code == 403
    assert c.get("/auth/status").json() == {"registration": "closed", "legacy": []}


def test_cross_origin_write_refused(ctx):
    c, _ = ctx
    r = c.post("/auth/login", json={"email": "a@example.org", "password": PW},
               headers={"Origin": "https://evil.example"})
    assert r.status_code == 403


def test_cookie_secure_only_behind_https(ctx):
    c, _ = ctx
    r = reg(c, email="http@example.org")
    assert "secure" not in r.headers["set-cookie"].lower()
    c.post("/auth/logout")
    r = c.post("/auth/login", json={"email": "http@example.org", "password": PW},
               headers={"X-Forwarded-Proto": "https"})
    assert "secure" in r.headers["set-cookie"].lower()


def test_change_password(ctx):
    c, _ = ctx
    reg(c, email="cp@example.org")
    c.post("/auth/logout")
    c.post("/auth/login", json={"email": "cp@example.org", "password": PW})
    bad = {"current": "mauvais-mdp-long", "new": "nouveau-mdp-solide"}
    assert c.post("/auth/change-password", json=bad).status_code == 401
    assert c.post("/auth/change-password", json={"current": PW, "new": "court"}).status_code == 422
    assert c.post("/auth/change-password", json={"current": PW, "new": "nouveau-mdp-solide"}).status_code == 200
    assert c.get("/auth/me").status_code == 200  # la session courante reste ouverte
    c.post("/auth/logout")
    assert c.post("/auth/login", json={"email": "cp@example.org", "password": PW}).status_code == 401
    assert c.post("/auth/login", json={"email": "cp@example.org", "password": "nouveau-mdp-solide"}).status_code == 200
