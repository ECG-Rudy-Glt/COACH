"""Parcours : séance reliée à une activité importée -> courbes (FC avec zones, allure, altitude), tableau en alternative, résumé prévu/fait, aucune position GPS affichée."""
import base64
from datetime import UTC, datetime

from playwright.sync_api import Page, expect

from .conftest import DEMO_EMAIL, DEMO_PASSWORD, login, tab


def _tcx() -> bytes:
    start = datetime.now(UTC).replace(hour=0, minute=5, second=0, microsecond=0)
    iso = lambda s: datetime.fromtimestamp(start.timestamp() + s, UTC).strftime("%Y-%m-%dT%H:%M:%SZ")  # noqa: E731
    pts = "".join(f"<Trackpoint><Time>{iso(i * 10)}</Time><Position><LatitudeDegrees>48.85</LatitudeDegrees><LongitudeDegrees>2.35</LongitudeDegrees></Position>"
                  f"<AltitudeMeters>{100 + i / 5}</AltitudeMeters><DistanceMeters>{i * 31}</DistanceMeters><HeartRateBpm><Value>{125 + i // 3}</Value></HeartRateBpm>"
                  f'<Extensions><TPX xmlns="http://www.garmin.com/xmlschemas/ActivityExtension/v2"><Speed>3.1</Speed></TPX></Extensions></Trackpoint>' for i in range(162))
    ns = "http://www.garmin.com/xmlschemas/TrainingCenterDatabase/v2"
    return (f'<?xml version="1.0"?><TrainingCenterDatabase xmlns="{ns}"><Activities><Activity Sport="Swimming"><Id>{iso(0)}</Id>'
            f'<Lap StartTime="{iso(0)}"><TotalTimeSeconds>1620</TotalTimeSeconds><DistanceMeters>5022</DistanceMeters>'
            f"<Track>{pts}</Track></Lap></Activity></Activities></TrainingCenterDatabase>").encode()


def test_session_curves_from_an_imported_file(page: Page, base_url: str):
    origin = {"Origin": base_url}
    page.request.post("/auth/login", data={"email": DEMO_EMAIL, "password": DEMO_PASSWORD}, headers=origin)
    page.request.put("/auth/language", data={"lang": "fr"}, headers=origin)
    uid = page.request.get("/auth/me").json()["id"]
    r = page.request.post(f"/users/{uid}/activities/import", data={"files": [{"name": "sortie.tcx", "data": base64.b64encode(_tcx()).decode()}], "tz": "UTC"}, headers=origin)
    assert r.json()["imported"] == 1, r.text()
    day = r.json()["results"][0]["activity"]["day"]
    sess = page.request.post(f"/users/{uid}/plan/sessions", data={"day": day, "kind": "sport_swim", "title": "Nage courbes", "duration_min": 27}, headers=origin).json()
    acts = page.request.get(f"/users/{uid}/garmin").json()["recent"]
    gid = next(a["garmin_id"] for a in acts if a["source"] == "tcx")
    assert page.request.post(f"/users/{uid}/plan/sessions/{sess['id']}/link", data={"garmin_id": gid}, headers=origin).ok
    page.context.clear_cookies()
    login(page)
    tab(page, "Plan")
    page.locator("button.sess", has_text="Nage courbes").click()
    card = page.locator("div.card", has=page.get_by_role("heading", name="Courbes de la séance"))
    expect(card.get_by_role("img", name="Fréquence cardiaque au fil de la séance", exact=False)).to_be_visible()
    expect(card.get_by_role("img", name="Vitesse au fil de la séance", exact=False)).to_be_visible()
    expect(card.get_by_role("img", name="Altitude au fil de la séance", exact=False)).to_be_visible()
    expect(card.get_by_text("Fait (séance ajoutée hors plan", exact=False)).to_be_visible()
    card.get_by_text("Voir les valeurs").first.click()
    expect(card.locator("details.st-table table").first).to_be_visible()
    expect(card.get_by_text("Kilomètres", exact=True)).to_be_visible()
    assert "48.85" not in card.inner_html() and "latitude" not in card.inner_html().lower()  # aucune position GPS dans l'interface
    page.request.delete(f"/users/{uid}/plan/sessions/{sess['id']}", headers=origin)  # la séance d'essai ne doit pas gêner les autres parcours (serveur partagé)
