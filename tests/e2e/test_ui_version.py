"""Parcours : le Profil affiche la version de l'interface exécutée, et le service worker revalide les fichiers (pas de cache HTTP périmé)."""
from playwright.sync_api import Page, expect

from .conftest import DEMO_EMAIL, DEMO_PASSWORD, login, tab


def test_profile_shows_ui_build(page: Page, base_url: str):
    origin = {"Origin": base_url}
    page.request.post("/auth/login", data={"email": DEMO_EMAIL, "password": DEMO_PASSWORD}, headers=origin)
    page.request.put("/auth/language", data={"lang": "fr"}, headers=origin)
    page.context.clear_cookies()
    login(page)
    tab(page, "Profil")
    page.get_by_text("Compte et sécurité").click()
    expect(page.locator("#ui-build")).to_contain_text("Interface : sc-v")
    assert "no-cache" in (page.request.get("/sw.js").headers.get("cache-control") or "")


def test_profile_shows_ai_cost_card(page: Page, base_url: str):
    login(page)
    tab(page, "Profil")
    page.get_by_text("Préférences").click()
    bar = page.locator("#ai-cost [role=progressbar]")
    expect(bar).to_have_attribute("aria-valuenow", "0")
    expect(page.locator("#ai-cost")).to_contain_text("Dépensé ≈")
    expect(page.locator("#ai-cost")).to_contain_text("la facture du fournisseur fait foi")
