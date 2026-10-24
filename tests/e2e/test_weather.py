"""Parcours : Profil > Préférences > choisir sa ville active la météo ; le Plan affiche un badge par séance en extérieur et, au détail, la prévision et la règle citée."""
from playwright.sync_api import Page, expect

from .conftest import DEMO_EMAIL, DEMO_PASSWORD, login, tab


def test_weather_setting_badge_and_detail(page: Page, base_url: str):
    origin = {"Origin": base_url}
    page.request.post("/auth/login", data={"email": DEMO_EMAIL, "password": DEMO_PASSWORD}, headers=origin)
    page.request.put("/auth/language", data={"lang": "fr"}, headers=origin)
    page.context.clear_cookies()
    login(page)
    tab(page, "Plan")
    expect(page.locator(".wx")).to_have_count(0)  # désactivée par défaut : aucun badge
    tab(page, "Profil")
    page.get_by_text("Préférences").click()
    expect(page.get_by_text("Choisissez votre ville pour activer la météo.")).to_be_visible()
    expect(page.get_by_label("Prévoir mes sorties selon la météo")).to_be_disabled()
    page.get_by_label("Ville", exact=True).fill("Lyon")
    page.get_by_role("button", name="Chercher").click()
    page.get_by_role("button", name="Lyon").click()
    expect(page.get_by_label("Prévoir mes sorties selon la météo")).to_be_checked()
    expect(page.get_by_text("Ville : Lyon")).to_be_visible()
    tab(page, "Plan")
    badge = page.locator(".wx").first
    expect(badge).to_contain_text("Météo déconseillée")
    badge.click()
    expect(page.get_by_text("Rafales prévues jusqu'à 70 km/h")).not_to_be_visible()  # explication repliée par défaut
    page.get_by_text("Pourquoi cette météo").click()
    page.get_by_text("À savoir", exact=True).click()
    expect(page.get_by_text("Rafales prévues jusqu'à 70 km/h")).to_be_visible()
    expect(page.get_by_text("(W2)")).to_be_visible()
    expect(page.get_by_text("jamais un avis médical")).to_be_visible()
