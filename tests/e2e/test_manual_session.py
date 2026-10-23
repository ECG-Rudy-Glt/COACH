"""Parcours : Plan > ajouter une séance faite hors plan, saisir ses exercices, la retrouver dans la semaine, la supprimer."""
from playwright.sync_api import Page, expect

from .conftest import DEMO_EMAIL, DEMO_PASSWORD, login, tab


def test_add_manual_session(page: Page, base_url: str):
    origin = {"Origin": base_url}  # le parcours « English » enregistre l'anglais sur le compte de démo : on le remet en français
    page.request.post("/auth/login", data={"email": DEMO_EMAIL, "password": DEMO_PASSWORD}, headers=origin)
    page.request.put("/auth/language", data={"lang": "fr"}, headers=origin)
    page.context.clear_cookies()
    login(page)
    logged = page
    tab(logged, "Plan")
    logged.get_by_role("button", name="Ajouter une séance faite").click()
    sheet = logged.get_by_role("dialog", name="Ajouter une séance faite")
    sheet.get_by_label("Nom (facultatif)").fill("Dos biceps")
    sheet.get_by_label("Durée (min)").fill("50")
    sheet.get_by_role("button", name="Ajouter la séance").click()
    expect(logged.get_by_role("heading", name="Dos biceps", level=1)).to_be_visible()
    logged.get_by_label("Nom de l'exercice").fill("Tirage vertical")
    logged.get_by_role("button", name="Ajouter", exact=True).click()
    logged.get_by_label("Tirage vertical, série 1, kg").fill("55")
    logged.get_by_label("Tirage vertical, série 1, répétitions").fill("10")
    expect(logged.get_by_text("Enregistré", exact=True)).to_be_visible()
    logged.get_by_role("button", name="Enregistrer la séance").click()
    row = logged.locator("button.sess", has_text="Dos biceps")
    expect(row).to_contain_text("ajoutée")
    row.click()
    expect(logged.get_by_label("Tirage vertical, série 1, kg")).to_have_value("55")  # la saisie est relue depuis le serveur
    delete = logged.get_by_role("button", name="Supprimer cette séance")
    delete.click()
    logged.get_by_role("button", name="Confirmer la suppression").click()
    expect(logged.get_by_role("heading", name="Mon plan")).to_be_visible()
    expect(logged.locator("button.sess", has_text="Dos biceps")).to_have_count(0)
