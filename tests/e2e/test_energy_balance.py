"""Parcours : Nutrition affiche la carte « Bilan du jour » (jour courant « à ce stade », objectif inchangé, estimations signalées)."""
from playwright.sync_api import Page, expect

from .conftest import DEMO_EMAIL, DEMO_PASSWORD, login, tab


def test_day_balance_card(page: Page, base_url: str):
    origin = {"Origin": base_url}
    page.request.post("/auth/login", data={"email": DEMO_EMAIL, "password": DEMO_PASSWORD}, headers=origin)
    page.request.put("/auth/language", data={"lang": "fr"}, headers=origin)
    page.context.clear_cookies()
    login(page)
    tab(page, "Nutrition")
    card = page.locator(".card", has=page.get_by_role("heading", name="Bilan du jour"))
    expect(card).to_be_visible()
    expect(card).to_contain_text("À ce stade")
    expect(card).to_contain_text("Dépense à ce stade")
    expect(card).to_contain_text("≈")
    expect(card).to_contain_text("Objectif du jour")
    expect(card).to_contain_text("n'oblige pas à manger plus")
