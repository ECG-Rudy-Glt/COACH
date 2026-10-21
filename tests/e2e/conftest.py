"""Tests de parcours de l'interface : vrai serveur (MemoryRepo + faux LLM, voir serve.py) et Chromium sans interface, écran de téléphone.

Lancés à part de `pytest -q` (pytest.ini les ignore) : `pytest tests/e2e -o addopts=`. Voir CONTRIBUTING.md.
"""
import os
import socket
import subprocess
import sys
import time
import urllib.error
import urllib.request
from pathlib import Path

import pytest

pytest.importorskip("playwright", reason="pip install -r requirements-e2e.txt && playwright install chromium")

from playwright.sync_api import Browser, Page, expect, sync_playwright  # noqa: E402

HERE = Path(__file__).resolve().parent
DEMO_EMAIL, DEMO_PASSWORD = "demo@example.org", "demo-password-123"  # compte synthétique créé par scripts/demo_server.py
expect.set_options(timeout=10_000)


def _free_port() -> int:
    with socket.socket() as s:
        s.bind(("127.0.0.1", 0))
        return int(s.getsockname()[1])


@pytest.fixture(scope="session")
def base_url():
    port = _free_port()
    env = {**os.environ, "TZ": "UTC", "PYTHONUNBUFFERED": "1"}
    for k in ("DATABASE_URL", "TEST_DATABASE_URL", "DB_HOST"):
        env.pop(k, None)
    proc = subprocess.Popen([sys.executable, str(HERE / "serve.py"), str(port)], env=env, stdout=subprocess.DEVNULL, stderr=subprocess.PIPE)
    url = f"http://127.0.0.1:{port}"
    deadline = time.monotonic() + 60
    while True:
        if proc.poll() is not None:
            raise RuntimeError("Le serveur d'essai s'est arrêté : " + (proc.stderr.read() or b"").decode()[-2000:])
        try:
            urllib.request.urlopen(url + "/healthz", timeout=2).read()
            break
        except (urllib.error.URLError, OSError):
            if time.monotonic() > deadline:
                proc.kill()
                raise RuntimeError("Le serveur d'essai ne répond pas.") from None
            time.sleep(0.2)  # interrogation du serveur au démarrage, pas une attente de l'interface
    yield url
    proc.terminate()
    try:
        proc.wait(10)
    except subprocess.TimeoutExpired:
        proc.kill()


@pytest.fixture(scope="session")
def browser():
    with sync_playwright() as p:
        exe = os.environ.get("CHROMIUM_PATH")  # sinon le Chromium installé par `playwright install chromium`
        b = p.chromium.launch(executable_path=exe) if exe else p.chromium.launch()
        yield b
        b.close()


@pytest.fixture
def page(browser: Browser, base_url: str):
    """Une page neuve par test (contexte isolé : cookies et stockage vides), 390 px, sans service worker. Échoue si la page lève une erreur JavaScript."""
    ctx = browser.new_context(viewport={"width": 390, "height": 844}, is_mobile=True, has_touch=True, locale="fr-FR", timezone_id="UTC",
                              service_workers="block", base_url=base_url)
    pg = ctx.new_page()
    pg.set_default_timeout(10_000)
    errors: list[str] = []
    pg.on("pageerror", lambda e: errors.append(f"{e}\n{e.stack or ''}"))
    pg.errors = errors  # type: ignore[attr-defined]
    yield pg
    ctx.close()
    assert not errors, "Erreur JavaScript dans la page :\n" + "\n".join(errors)


def login(pg: Page, email: str = DEMO_EMAIL, password: str = DEMO_PASSWORD) -> None:
    pg.goto("/")
    pg.get_by_label("Email").fill(email)
    pg.get_by_label("Mot de passe").fill(password)
    pg.get_by_role("button", name="Se connecter").click()
    expect(pg.locator(".tabbar")).to_be_visible()


@pytest.fixture
def logged(page: Page) -> Page:
    login(page)
    return page


def tab(pg: Page, label: str) -> None:
    pg.locator(".tabbar button", has_text=label).click()
