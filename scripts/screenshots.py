"""Takes the README screenshots from the demo instance (synthetic data).

    pip install playwright                      # dev only, not a runtime dependency
    .venv/bin/python scripts/demo_server.py &   # serves http://127.0.0.1:8765
    python scripts/screenshots.py [base_url] [out_dir]

Uses an installed Chromium/Chrome: set CHROMIUM_PATH, or run `playwright install chromium` once.
"""
import os
import sys
from pathlib import Path

from playwright.sync_api import Page, sync_playwright

BASE = sys.argv[1] if len(sys.argv) > 1 else "http://127.0.0.1:8765"
OUT = Path(sys.argv[2] if len(sys.argv) > 2 else Path(__file__).resolve().parent.parent / "docs" / "img")
EMAIL, PASSWORD = "demo@example.org", "demo-password-123"
THEMES = ("light", "dark", "eco")


def shot(page: Page, name: str, full: bool = False) -> None:
    page.wait_for_timeout(500)
    page.screenshot(path=str(OUT / f"{name}.png"), full_page=full)
    print("saved", name)


def tab(page: Page, label: str) -> None:
    page.locator(".tabbar button", has_text=label).click()
    page.wait_for_timeout(700)


def run() -> None:
    OUT.mkdir(parents=True, exist_ok=True)
    with sync_playwright() as p:
        exe = os.environ.get("CHROMIUM_PATH")
        browser = p.chromium.launch(executable_path=exe) if exe else p.chromium.launch()
        ctx = browser.new_context(viewport={"width": 390, "height": 844}, device_scale_factor=2, is_mobile=True, has_touch=True,
                                  locale="fr-FR", timezone_id="Europe/Paris", service_workers="block")
        page = ctx.new_page()
        page.goto(BASE)
        page.fill('input[type="email"]', EMAIL)
        page.fill('input[type="password"]', PASSWORD)
        page.locator("form button[type=submit], button:has-text('Se connecter')").first.click()
        page.wait_for_selector(".tabbar", timeout=10000)
        for theme in THEMES:
            page.evaluate(f"localStorage.setItem('theme', '{theme}')")
            page.reload()
            page.wait_for_selector(".tabbar")
            tab(page, "Accueil")
            shot(page, f"home-{theme}")
            if theme == "light":
                tab(page, "Plan")
                shot(page, "plan-light")
                page.locator("text=Footing facile").first.click()
                page.wait_for_timeout(700)
                shot(page, "session-light")
                page.reload()
                page.wait_for_selector(".tabbar")
                tab(page, "Nutrition")
                shot(page, "nutrition-light")
                tab(page, "Profil")
                shot(page, "profile-light")
            if theme == "dark":
                tab(page, "Plan")
                shot(page, "plan-dark")
            if theme == "eco":
                tab(page, "Nutrition")
                shot(page, "nutrition-eco")
        browser.close()


if __name__ == "__main__":
    run()
