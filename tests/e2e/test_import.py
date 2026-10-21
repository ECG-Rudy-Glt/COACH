"""Parcours : Profil > Préférences > importer un fichier d'activité, résultat par fichier, doublon, fichier illisible."""
from datetime import UTC, datetime, timedelta

from playwright.sync_api import Page, expect

from .conftest import tab


def _tcx() -> bytes:
    start = (datetime.now(UTC) - timedelta(days=40)).replace(hour=3, minute=17, second=0, microsecond=0).strftime("%Y-%m-%dT%H:%M:%SZ")
    return (f'<?xml version="1.0"?><TrainingCenterDatabase xmlns="http://www.garmin.com/xmlschemas/TrainingCenterDatabase/v2"><Activities><Activity Sport="Running">'
            f'<Id>{start}</Id><Lap StartTime="{start}"><TotalTimeSeconds>1800</TotalTimeSeconds><DistanceMeters>5000</DistanceMeters><Calories>300</Calories>'
            f"</Lap></Activity></Activities></TrainingCenterDatabase>").encode()


def test_import_activity_files(logged: Page):
    tab(logged, "Profil")
    logged.locator("details.fold summary", has_text="Préférences").click()
    logged.get_by_role("button", name="Importer des fichiers FIT, TCX, GPX").click()
    expect(logged.get_by_role("heading", name="Importer des activités", level=1)).to_be_visible()
    files = logged.locator("#imp-files")
    files.set_input_files([{"name": "course.tcx", "mimeType": "application/octet-stream", "buffer": _tcx()},
                           {"name": "casse.fit", "mimeType": "application/octet-stream", "buffer": b"pas une activite"}])
    expect(logged.locator(".item", has_text="course.tcx").get_by_text("Importée")).to_be_visible()
    expect(logged.locator(".item", has_text="casse.fit").get_by_text("Illisible")).to_be_visible()
    expect(logged.get_by_role("button", name="Voir le plan")).to_be_visible()
    files.set_input_files([{"name": "course.tcx", "mimeType": "application/octet-stream", "buffer": _tcx()}])
    expect(logged.locator(".item", has_text="course.tcx").get_by_text("Doublon")).to_be_visible()
