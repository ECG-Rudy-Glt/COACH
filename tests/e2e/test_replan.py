"""Parcours : Plan > Replanifier la fin de semaine : aperçu (pourquoi replié avec ses sources), annulation de l'aperçu, acceptation puis annulation de la trace ; 390 px sans débordement."""
from playwright.sync_api import Page, expect

from .conftest import DEMO_EMAIL, DEMO_PASSWORD, login, tab


def test_replan_rest_of_week(page: Page, base_url: str):
    origin = {"Origin": base_url}
    page.request.post("/auth/login", data={"email": DEMO_EMAIL, "password": DEMO_PASSWORD}, headers=origin)
    page.request.put("/auth/language", data={"lang": "fr"}, headers=origin)
    page.context.clear_cookies()
    login(page)
    tab(page, "Plan")
    button = page.get_by_role("button", name="Replanifier la fin de semaine")
    if not button.count():
        return  # la démonstration n'a plus de séance prévue cette semaine (dimanche) : rien à replanifier
    button.click()
    sheet = page.get_by_role("dialog", name="Replanifier la fin de semaine")
    expect(sheet).to_be_visible()
    accept = sheet.get_by_role("button", name="Accepter")
    if not accept.count():
        expect(sheet).to_contain_text("Rien à replanifier")
        return
    why = sheet.locator("details.more", has_text="Pourquoi ces choix")
    expect(why).to_be_visible()
    assert not why.evaluate("d => d.open")  # replié par défaut
    why.locator("summary").click()
    expect(why).to_contain_text("G13")
    width = page.evaluate("() => [document.documentElement.scrollWidth, window.innerWidth, document.querySelector('.sheet').scrollWidth, document.querySelector('.sheet').clientWidth]")
    assert width[0] <= width[1] and width[2] <= width[3], width  # aucun débordement à 390 px
    sheet.get_by_role("button", name="Annuler").click()
    expect(sheet).to_have_count(0)
    page.get_by_role("button", name="Replanifier la fin de semaine").click()
    page.get_by_role("dialog", name="Replanifier la fin de semaine").get_by_role("button", name="Accepter").click()
    undo = page.get_by_role("button", name="Annuler la dernière replanification")
    expect(undo).to_be_visible()
    undo.click()
    expect(page.get_by_role("button", name="Annuler la dernière replanification")).to_have_count(0)


PROPOSAL = {
    "week": "2026-10-05", "from": "2026-10-08", "empty": False, "fingerprint": "abcdef0123456789", "explanation": "Votre footing passe à demain pour garder la sortie longue du week-end.",
    "changes": [{"session_id": 1, "title": "Footing facile", "kind": "run_easy", "from": "2026-10-07", "to": "2026-10-08", "duration_from": 45, "duration_to": 50, "action": "move", "missed": True},
                {"session_id": 2, "title": "Haut du corps, tirage et poussée", "kind": "strength_upper", "from": "2026-10-07", "to": None,
                 "duration_from": 50, "duration_to": None, "action": "drop", "missed": True},
                {"session_id": 3, "title": "Sortie longue", "kind": "run_long", "from": "2026-10-10", "to": "2026-10-10", "duration_from": 80, "duration_to": 80, "action": "keep", "missed": False}],
    "days": [{"day": "2026-10-08", "blocked": False, "sessions": [{"session_id": 1, "title": "Footing facile", "kind": "run_easy", "duration_min": 50}]},
             {"day": "2026-10-09", "blocked": True, "sessions": []},
             {"day": "2026-10-10", "blocked": False, "sessions": [{"session_id": 3, "title": "Sortie longue", "kind": "run_long", "duration_min": 80}]},
             {"day": "2026-10-11", "blocked": False, "sessions": []}],
    "applied": [{"rule": "G13", "text": "Seules les séances prévues pour cette semaine sont replacées : aucune n'est ajoutée, une séance manquée n'est jamais doublée, "
                         "la phase et le volume du plan ne changent pas.",
                 "ids": [], "convention": True, "sources": []},
                {"rule": "G14", "text": "Le volume de course de la semaine (fait + à venir) ne dépasse pas celui prévu, "
                         "donc la hausse reste dans le plafond de la semaine (G1).", "ids": ["RUN-005"], "convention": True,
                 "sources": [{"id": "RUN-005", "citation": "Buist 2008", "url": "https://pubmed.ncbi.nlm.nih.gov/17940147/"}]}],
    "notes": ["« Haut du corps, tirage et poussée » est retirée de cette semaine : aucun jour restant ne la place sans entasser les séances dures ni enfreindre vos limites (G15, G17)."],
    "volume": {"target_min": 170, "done_min": 60, "planned_min": 100, "lost_pct": 6},
}


def test_replan_sheet_with_a_known_proposal(page: Page, base_url: str):
    """Aperçu synthétique (la date du jour de l'essai ne garantit pas de séance à venir) : mise en page, pourquoi replié, sources, acceptation."""
    origin = {"Origin": base_url}
    page.request.post("/auth/login", data={"email": DEMO_EMAIL, "password": DEMO_PASSWORD}, headers=origin)
    page.request.put("/auth/language", data={"lang": "fr"}, headers=origin)
    page.context.clear_cookies()
    login(page)
    applied: list[str] = []
    page.route("**/plan/replan/preview", lambda r: r.fulfill(json=PROPOSAL))
    page.route("**/plan/replan/apply", lambda r: (applied.append(r.request.post_data or ""), r.fulfill(json={"id": 1, "changed": 2}))[1])
    page.evaluate("() => replanSheet(() => {})")
    sheet = page.get_by_role("dialog", name="Replanifier la fin de semaine")
    expect(sheet).to_contain_text("Footing facile")
    expect(sheet).to_contain_text("manquée le")
    expect(sheet).to_contain_text("Retirée de la semaine")
    why = sheet.locator("details.more", has_text="Pourquoi ces choix")
    assert not why.evaluate("d => d.open")
    why.locator("summary").click()
    expect(why.get_by_role("link", name="RUN-005")).to_have_attribute("href", "https://pubmed.ncbi.nlm.nih.gov/17940147/")
    expect(why).to_contain_text("conventions de pratique")
    dims = page.evaluate("() => { const s = document.querySelector('.sheet'); return [document.documentElement.scrollWidth, window.innerWidth, s.scrollWidth, s.clientWidth]; }")
    assert dims[0] <= dims[1] and dims[2] <= dims[3], dims
    shot = __import__("os").environ.get("REPLAN_SHOT")
    if shot:
        page.screenshot(path=shot)
    sheet.get_by_role("button", name="Accepter").click()
    expect(sheet).to_have_count(0)
    assert "abcdef0123456789" in applied[0]
