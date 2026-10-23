"""Parcours : ajouter une course faite hors plan avec distance, allure, FC, ressenti et commentaire, la relire, la supprimer."""
from playwright.sync_api import Page, expect

from .conftest import DEMO_EMAIL, DEMO_PASSWORD, login, tab


def test_add_manual_run(page: Page, base_url: str):
    origin = {"Origin": base_url}
    page.request.post("/auth/login", data={"email": DEMO_EMAIL, "password": DEMO_PASSWORD}, headers=origin)
    page.request.put("/auth/language", data={"lang": "fr"}, headers=origin)
    page.context.clear_cookies()
    login(page)
    tab(page, "Plan")
    page.get_by_role("button", name="Ajouter une séance faite").click()
    sheet = page.get_by_role("dialog", name="Ajouter une séance faite")
    sheet.get_by_label("Type").select_option("run_easy")
    sheet.get_by_label("Nom (facultatif)").fill("Footing du soir")
    sheet.get_by_label("Durée (min)").fill("50")
    sheet.get_by_role("button", name="Ajouter la séance").click()
    expect(page.get_by_role("heading", name="Footing du soir", level=1)).to_be_visible()
    page.get_by_label("Distance (km)", exact=True).first.fill("10")
    expect(page.get_by_label("Allure moyenne (min par km)")).to_have_value("5:00")  # déduite de la distance et de la durée
    page.get_by_label("Fréquence cardiaque moyenne (facultatif)").fill("150")
    page.get_by_label("Effort ressenti").select_option("6")
    page.get_by_label("Commentaire").fill("Bonnes jambes")
    expect(page.get_by_text("Enregistré", exact=True)).to_be_visible()
    page.get_by_role("button", name="Enregistrer la séance").click()
    row = page.locator("button.sess", has_text="Footing du soir")
    expect(row).to_contain_text("ajoutée")
    row.click()
    expect(page.get_by_label("Allure moyenne (min par km)")).to_have_value("5:00")
    expect(page.get_by_label("Commentaire")).to_have_value("Bonnes jambes")
    page.get_by_role("button", name="Supprimer cette séance").click()
    page.get_by_role("button", name="Confirmer la suppression").click()
    expect(page.locator("button.sess", has_text="Footing du soir")).to_have_count(0)
