"""Parcours minimaux de l'interface sur un téléphone (390 px). Ils attrapent ce que `node --check` ne voit pas : variable supprimée,
fonction écrasée par un autre fichier, écran qui plante au rendu. La fixture `page` échoue au moindre pageerror."""
import re
from itertools import count

from playwright.sync_api import Page, expect

from .conftest import tab

_uid = count(1)


def test_register_then_login(page: Page):
    email = f"nouveau{next(_uid)}@example.org"
    page.goto("/")
    page.get_by_role("button", name="Créer un compte").click()
    page.get_by_label("Prénom").fill("Sam")
    page.get_by_label("Email").fill(email)
    page.get_by_label("Mot de passe").fill("un-mot-de-passe-long-123")
    page.get_by_role("button", name="Créer mon compte").click()
    expect(page.get_by_role("heading", level=1)).not_to_have_text("Créer votre compte")  # on est passé à l'écran suivant (questionnaire ou accueil)
    page.context.clear_cookies()
    page.goto("/")
    page.get_by_label("Email").fill(email)
    page.get_by_label("Mot de passe").fill("un-mot-de-passe-long-123")
    page.get_by_role("button", name="Se connecter").click()
    expect(page.get_by_role("heading", level=1)).not_to_have_text("Content de vous revoir.")


def test_login_wrong_password_shows_error(page: Page):
    page.goto("/")
    page.get_by_label("Email").fill("demo@example.org")
    page.get_by_label("Mot de passe").fill("mauvais-mot-de-passe")
    page.get_by_role("button", name="Se connecter").click()
    expect(page.locator("p.error")).not_to_be_empty()
    expect(page.locator(".tabbar")).to_have_count(0)


def test_add_meal_with_estimate(logged: Page):
    tab(logged, "Nutrition")
    expect(logged.get_by_role("heading", name="Nutrition", exact=True)).to_be_visible()
    logged.get_by_role("button", name="Ajouter un repas").click()
    logged.get_by_label("Description du repas").fill("Assiette de test e2e simple")
    logged.get_by_role("button", name="Enregistrer").click()
    card = logged.locator(".card", has_text="Assiette de test e2e simple")
    expect(card).to_be_visible()
    expect(card).to_contain_text("650 kcal")  # estimation du faux LLM
    expect(logged.locator("strong", has_text="Aujourd'hui")).to_be_visible()


def test_lunchbox_lands_on_tomorrow(logged: Page):
    tab(logged, "Nutrition")
    logged.get_by_role("button", name="Ajouter un repas").click()
    logged.get_by_label("Description du repas").fill("Gamelle de test e2e")
    logged.get_by_label("Gamelle pour demain midi").check()
    logged.get_by_role("button", name="Enregistrer").click()
    expect(logged.locator("strong", has_text="Demain")).to_be_visible()
    expect(logged.locator(".card", has_text="Gamelle de test e2e")).to_be_visible()
    logged.get_by_role("button", name="Jour précédent").click()
    expect(logged.locator("strong", has_text="Aujourd'hui")).to_be_visible()
    expect(logged.get_by_text("Gamelle de test e2e")).to_have_count(0)


def test_nutrition_screen(logged: Page):
    tab(logged, "Nutrition")
    expect(logged.get_by_role("heading", name="Suivi du poids")).to_be_visible()
    expect(logged.get_by_role("button", name="3 mois")).to_have_attribute("aria-pressed", "true")  # période par défaut
    expect(logged.get_by_text("moyenne sur 7 jours")).to_have_count(0)
    expect(logged.get_by_text(re.compile("^Tendance")).first).to_be_visible()  # chiffrée ou « non calculée » (démo : une pesée par semaine)
    logged.get_by_role("button", name="12 mois").click()
    expect(logged.get_by_role("button", name="12 mois")).to_have_attribute("aria-pressed", "true")
    expect(logged.locator("svg[aria-label*='Courbe de poids sur 12 mois']")).to_be_visible()
    expect(logged.get_by_text("Poulet, riz, brocolis")).to_be_visible()  # repas du compte de démonstration
    expect(logged.get_by_role("button", name="Ajouter un repas")).to_be_visible()


def test_plan_screen(logged: Page):
    tab(logged, "Plan")
    expect(logged.get_by_role("heading", name="Mon plan")).to_be_visible()
    expect(logged.get_by_text("Footing facile").first).to_be_visible()
    logged.get_by_text("Footing facile").first.click()
    expect(logged.get_by_role("button", name="Retour").first).to_be_visible()  # détail d'une séance


def test_stats_screens(logged: Page):
    logged.get_by_role("button", name="Voir").last.click()  # carte « Statistiques » de l'accueil
    expect(logged.get_by_role("heading", name="Statistiques", level=1)).to_be_visible()
    expect(logged.get_by_role("heading", name="Pas par jour")).to_be_visible()  # Quotidien
    for section, heading in (("Progression", "Records de course"), ("Forme", "Volume"), ("Quotidien", "Pas par jour")):
        logged.get_by_role("button", name=section, exact=True).click()
        expect(logged.get_by_role("heading", name=heading).first).to_be_visible()
    expect(logged.locator("p.error")).to_have_count(0)


def test_stats_sections_all_visible_without_scroll(logged: Page):
    logged.locator(".card", has_text="Pas, repas, poids").get_by_role("button", name="Voir").click()
    forme = logged.get_by_role("button", name="Forme", exact=True)
    expect(forme).to_be_visible()
    box = forme.bounding_box()
    assert box and box["x"] >= 0 and box["x"] + box["width"] <= 390 - 8, box  # entièrement dans l'écran, avec une marge
    assert logged.evaluate("document.querySelector('.st-seg').scrollWidth <= document.querySelector('.st-seg').clientWidth")
    forme.click()
    expect(logged.get_by_text("Pour faire apparaître l'araignée")).to_be_visible()  # moins de 3 axes : on explique quoi saisir


def test_profile_overview(logged: Page):
    tab(logged, "Profil")
    expect(logged.get_by_role("heading", name="Profil", level=1)).to_be_visible()
    expect(logged.get_by_text("Ma forme")).to_be_visible()  # l'araignée (ou, faute de 3 axes, ce qu'il faut saisir) est dans le Profil
    expect(logged.get_by_text("Pour faire apparaître l'araignée")).to_be_visible()
    expect(logged.locator(".item .v")).to_have_count(0)  # plus de liste de questions sur l'écran principal
    for rubrique in ("Identité", "Sports et objectifs", "Préférences", "Compte et sécurité"):
        expect(logged.locator("details.fold summary", has_text=rubrique)).to_be_visible()
    logged.locator("details.fold summary", has_text="Compte et sécurité").click()
    expect(logged.get_by_role("button", name="Se déconnecter")).to_be_visible()
    logged.get_by_role("button", name="Voir le détail dans Statistiques").click()
    expect(logged.get_by_role("heading", name="Statistiques", level=1)).to_be_visible()


def test_profile_questionnaire_edit(logged: Page):
    tab(logged, "Profil")
    logged.locator(".card", has_text="Questionnaire").get_by_role("button", name="Ouvrir").click()
    expect(logged.get_by_role("heading", name="Questionnaire", level=1)).to_be_visible()
    logged.locator("details.fold summary").first.click()
    logged.locator(".item").first.click()  # édition d'une réponse
    expect(logged.get_by_role("button", name="Retour")).to_be_visible()
    logged.get_by_role("button", name="Retour").click()
    expect(logged.get_by_role("heading", name="Questionnaire", level=1)).to_be_visible()


def test_switch_to_english(page: Page):
    page.goto("/")
    page.get_by_role("button", name="English").click()
    expect(page.get_by_role("heading", level=1)).to_have_text("Good to see you again.")
    expect(page.locator("html")).to_have_attribute("lang", "en")
    page.get_by_label("Email").fill("demo@example.org")
    page.get_by_label("Password").fill("demo-password-123")
    page.get_by_role("button", name="Sign in").click()
    expect(page.locator(".tabbar")).to_be_visible()
    tab(page, "Nutrition")
    page.get_by_role("button", name="Add a meal").click()
    expect(page.get_by_label(re.compile("Packed lunch for tomorrow"))).to_be_visible()
    page.reload()
    expect(page.locator(".tabbar")).to_be_visible()
    expect(page.locator("html")).to_have_attribute("lang", "en")  # le choix est gardé sur l'appareil


def test_theme_toggle(page: Page):
    page.goto("/")
    page.get_by_role("button", name="Sombre").click()
    expect(page.locator("html")).to_have_class("dark")
    page.reload()
    expect(page.locator("html")).to_have_class("dark")  # gardé sur l'appareil
