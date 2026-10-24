"""Parcours : les explications et détails de calcul sont repliés par défaut (résumé court visible) et se déplient au toucher ou au clavier."""
from playwright.sync_api import Page, expect

from .conftest import DEMO_EMAIL, DEMO_PASSWORD, login, tab


def _fr(page: Page, base_url: str) -> None:
    origin = {"Origin": base_url}
    page.request.post("/auth/login", data={"email": DEMO_EMAIL, "password": DEMO_PASSWORD}, headers=origin)
    page.request.put("/auth/language", data={"lang": "fr"}, headers=origin)
    page.context.clear_cookies()
    login(page)


def _no_overflow(page: Page) -> None:
    assert page.evaluate("document.documentElement.scrollWidth <= window.innerWidth"), "débordement horizontal"


def test_nutrition_details_are_folded_then_unfolded(page: Page, base_url: str):
    _fr(page, base_url)
    tab(page, "Nutrition")
    card = page.locator(".card", has=page.get_by_role("heading", name="Bilan du jour"))
    fold = card.locator("details.more", has_text="Détail du bilan")
    expect(fold).to_be_visible()
    expect(fold).not_to_have_attribute("open", "")
    expect(card.get_by_text("Dépense à ce stade")).not_to_be_visible()  # le détail est replié
    expect(card.get_by_text("Objectif du jour", exact=True)).to_be_visible()  # le résumé reste visible
    box = fold.locator("summary").bounding_box()
    assert box and box["height"] >= 44, box  # cible tactile
    fold.locator("summary").focus()
    page.keyboard.press("Enter")  # clavier : le <summary> natif se déplie
    expect(fold).to_have_attribute("open", "")
    expect(card.get_by_text("Dépense à ce stade")).to_be_visible()
    _no_overflow(page)


def test_stats_notes_are_folded(page: Page, base_url: str):
    _fr(page, base_url)
    page.locator(".card", has_text="Pas, repas, poids").get_by_role("button", name="Voir").click()
    expect(page.get_by_role("heading", name="Pas par jour")).to_be_visible()
    notes = page.locator("details.more", has_text="Comment lire ces chiffres").first
    expect(notes).to_be_visible()
    expect(notes).not_to_have_attribute("open", "")
    notes.locator("summary").click()
    expect(notes).to_have_attribute("open", "")
    _no_overflow(page)
