import pytest
from fastapi.testclient import TestClient

from app.auth import MAX_FAILS, reset_rate_limits
from app.main import app, get_repo
from app.repo import MemoryRepo

PW = "un-mot-de-passe-solide"


@pytest.fixture
def client():
    reset_rate_limits()
    repo = MemoryRepo()
    app.dependency_overrides[get_repo] = lambda: repo
    yield TestClient(app)
    app.dependency_overrides.clear()


def register(c, email="a@example.org"):
    return c.post("/auth/register", json={"name": "A", "email": email, "password": PW})


def test_security_headers_on_every_response(client):
    r = client.get("/healthz")
    assert "script-src 'self'" in r.headers["content-security-policy"]
    assert "frame-ancestors 'none'" in r.headers["content-security-policy"]
    assert r.headers["x-content-type-options"] == "nosniff" and r.headers["x-frame-options"] == "DENY"
    assert "strict-transport-security" not in r.headers
    assert "strict-transport-security" in client.get("/healthz", headers={"x-forwarded-proto": "https"}).headers


def test_no_inline_script_in_page(client):
    html = client.get("/").text
    assert "<script>" not in html  # la CSP interdit les scripts en ligne


def test_api_docs_disabled_by_default(client):
    assert client.get("/docs").status_code == 404
    assert client.get("/openapi.json").status_code == 404


def test_registration_first_mode(client, monkeypatch):
    monkeypatch.setenv("REGISTRATION", "first")
    assert client.get("/auth/status").json()["registration"] == "open"
    assert register(client).status_code == 201
    assert client.get("/auth/status").json()["registration"] == "closed"
    assert register(client, "b@example.org").status_code == 403


def test_registration_closed(client, monkeypatch):
    monkeypatch.setenv("REGISTRATION", "closed")
    assert register(client).status_code == 403


def test_cross_origin_write_refused(client):
    r = client.post("/auth/register", json={"name": "A", "email": "x@example.org", "password": PW}, headers={"origin": "https://evil.example"})
    assert r.status_code == 403


def test_forwarded_for_ignored_unless_trusted(client, monkeypatch):
    register(client)
    client.cookies.clear()
    monkeypatch.delenv("TRUST_PROXY", raising=False)
    for i in range(MAX_FAILS):  # une adresse falsifiée par essai ne contourne pas la limite
        client.post("/auth/login", json={"email": "a@example.org", "password": "mauvais-mdp-1"}, headers={"x-forwarded-for": f"9.9.9.{i}"})
    assert client.post("/auth/login", json={"email": "a@example.org", "password": PW}, headers={"x-forwarded-for": "8.8.8.8"}).status_code == 429


def test_per_account_limit_across_addresses(client, monkeypatch):
    register(client)
    client.cookies.clear()
    monkeypatch.setenv("TRUST_PROXY", "1")
    codes = [client.post("/auth/login", json={"email": "a@example.org", "password": "mauvais-mdp-1"}, headers={"x-forwarded-for": f"9.9.9.{i}"}).status_code
             for i in range(25)]
    assert codes[0] == 401 and codes[-1] == 429
    assert client.post("/auth/login", json={"email": "a@example.org", "password": PW}, headers={"x-forwarded-for": "1.2.3.4"}).status_code == 429


def test_users_cannot_read_each_other(client):
    a = register(client).json()["id"]
    client.cookies.clear()
    register(client, "b@example.org")
    assert client.get(f"/users/{a}/profile").status_code in (403, 404)
    client.cookies.clear()
    assert client.get(f"/users/{a}/profile").status_code == 401


def test_camera_allowed_for_own_origin_only_and_wasm_without_eval(client):
    r = client.get("/healthz")
    pp = r.headers["permissions-policy"]
    assert "camera=(self)" in pp and "microphone=()" in pp and "geolocation=()" in pp  # scan des codes-barres : caméra de l'origine, rien d'autre
    csp = r.headers["content-security-policy"]
    assert "script-src 'self' 'wasm-unsafe-eval';" in csp and "unsafe-eval" not in csp.replace("wasm-unsafe-eval", "") and "img-src 'self' data: blob:;" in csp
    w = client.get("/vendor/zxing_reader.wasm")
    assert w.status_code == 200 and w.headers["content-type"] == "application/wasm" and w.content[:4] == b"\0asm"
