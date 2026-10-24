"""Parcours : séance de force faite hors plan -> schéma des muscles et son tableau, vue de la semaine dans Statistiques ; message clair pour une course."""
from playwright.sync_api import Page, expect

from .conftest import DEMO_EMAIL, DEMO_PASSWORD, login, tab


def _add(page: Page, name: str, kind: str):
    page.get_by_role("button", name="Ajouter une séance faite").click()
    sheet = page.get_by_role("dialog", name="Ajouter une séance faite")
    sheet.get_by_label("Type").select_option(kind)
    sheet.get_by_label("Nom (facultatif)").fill(name)
    sheet.get_by_label("Durée (min)").fill("40")
    sheet.get_by_role("button", name="Ajouter la séance").click()
    expect(page.get_by_role("heading", name=name, level=1)).to_be_visible()


def test_muscle_diagram_week_view_and_run_message(page: Page, base_url: str):
    origin = {"Origin": base_url}
    page.request.post("/auth/login", data={"email": DEMO_EMAIL, "password": DEMO_PASSWORD}, headers=origin)
    page.request.put("/auth/language", data={"lang": "fr"}, headers=origin)
    page.context.clear_cookies()
    login(page)
    tab(page, "Plan")
    _add(page, "Gainage maison", "strength_full")
    card = page.locator("div.card", has=page.get_by_role("heading", name="Muscles travaillés"))
    expect(card).to_contain_text("Saisissez des séries")
    page.get_by_label("Nom de l'exercice").fill("Hundred (les cent)")
    page.get_by_role("button", name="Ajouter", exact=True).click()
    page.get_by_label("Hundred (les cent), série 1, répétitions").fill("20")
    figure = card.get_by_role("img")
    expect(figure).to_have_attribute("aria-label", "Schéma des muscles, face et dos. Principaux : Abdominaux. Secondaires : Épaules.")
    card.get_by_text("Voir les valeurs").click()
    expect(card.get_by_role("rowheader", name="Abdominaux")).to_be_visible()
    page.get_by_role("button", name="Enregistrer la séance").click()
    page.locator("button.sess", has_text="Gainage maison").click()
    expect(page.get_by_role("img", name="Schéma des muscles", exact=False)).to_be_visible()  # relu depuis le serveur
    page.get_by_role("button", name="Supprimer cette séance").click()
    page.get_by_role("button", name="Confirmer la suppression").click()
    expect(page.get_by_role("heading", name="Mon plan")).to_be_visible()
    _add(page, "Footing maison", "run_easy")
    expect(page.get_by_text("Pas de schéma musculaire pour la course")).to_be_visible()
    page.get_by_role("button", name="Supprimer cette séance").click()
    page.get_by_role("button", name="Confirmer la suppression").click()
    expect(page.get_by_role("heading", name="Mon plan")).to_be_visible()
