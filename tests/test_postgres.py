"""Test d'intégration : actif seulement si TEST_DATABASE_URL est défini."""
import os
from pathlib import Path

import pytest

from app.questionnaire.models import Fact, current_facts
from app.repo import PostgresRepo

DSN = os.environ.get("TEST_DATABASE_URL")
pytestmark = pytest.mark.skipif(not DSN, reason="TEST_DATABASE_URL non défini")


def test_roundtrip_and_supersede():
    repo = PostgresRepo(DSN)
    repo.migrate(Path(__file__).parent.parent / "db" / "migrations")
    repo.migrate(Path(__file__).parent.parent / "db" / "migrations")  # idempotent
    uid = repo.create_user("test")
    assert repo.user_exists(uid) and not repo.user_exists(-1)
    repo.add_facts(uid, [Fact(key="body.weight_kg", value=80)])
    repo.add_facts(uid, [Fact(key="body.weight_kg", value=78),
                         Fact(key="sports.practiced", value=["running", "autre"])])
    facts = repo.list_facts(uid)
    assert current_facts(facts)["body.weight_kg"] == 78
    assert current_facts(facts)["sports.practiced"] == ["running", "autre"]
    assert len(facts) == 3


def test_accounts_sessions_and_legacy_adoption():
    from datetime import UTC, datetime, timedelta

    repo = PostgresRepo(DSN)
    repo.migrate(Path(__file__).parent.parent / "db" / "migrations")
    legacy = repo.create_user("ancien")
    assert any(u["id"] == legacy for u in repo.list_legacy_users())
    assert repo.adopt_legacy_user(legacy, "Rudy", "adopt@example.org", "h")
    assert not repo.adopt_legacy_user(legacy, "X", "autre@example.org", "h")  # déjà repris
    assert repo.get_account("adopt@example.org")["id"] == legacy
    repo.create_session(legacy, "tok1", datetime.now(UTC) + timedelta(days=1))
    repo.create_session(legacy, "tok2", datetime.now(UTC) - timedelta(days=1))
    assert repo.get_session_user("tok1")["email"] == "adopt@example.org"
    assert repo.get_session_user("tok2") is None  # expirée
    repo.delete_session("tok1")
    assert repo.get_session_user("tok1") is None


def test_exercises_upsert_search_media():
    from app.exercises.models import Exercise, Media

    repo = PostgresRepo(DSN)
    repo.migrate(Path(__file__).parent.parent / "db" / "migrations")
    ex = Exercise(source="t", source_id="x1", sources=["t"], name="Squat zzz", name_en="Zzz squat",
                  muscles_primary=["quadriceps"], equipment=["barbell"], license="L",
                  media=[Media(kind="image", url="https://wger.de/a.webp", is_main=True, license="CC", author="a")])
    assert repo.replace_exercises([ex]) == 1
    ex.name = "Squat zzz v2"
    ex.media = []
    repo.replace_exercises([ex])  # upsert : même clé, médias remplacés
    rows, total = repo.search_exercises("zzz", "quadriceps", "barbell", None, 10, 0)
    assert total == 1 and rows[0].name == "Squat zzz v2" and rows[0].media == []
    assert repo.get_exercise(rows[0].id).license == "L"
    assert repo.get_media(999999) is None


def test_garmin_storage_roundtrip():
    from datetime import date, datetime

    repo = PostgresRepo(DSN)
    repo.migrate(Path(__file__).parent.parent / "db" / "migrations")
    uid = repo.create_user("gm")
    repo.save_garmin(uid, "g@x.fr", "enc")
    repo.touch_garmin(uid, "enc2", None)
    a = repo.get_garmin(uid)
    assert a["tokens_enc"] == "enc2" and a["last_sync_at"] is not None
    row = {"garmin_id": "1", "day": date(2026, 10, 1), "started_at": datetime(2026, 10, 1, 7, 0), "sport": "run", "type_key": "running",
           "name": "Sortie", "duration_s": 3000, "distance_m": 9000.0, "elevation_m": 50.0, "avg_hr": 150, "max_hr": 170,
           "calories": 500, "training_load": 80.0}
    assert repo.upsert_activities(uid, [row]) == 1
    assert repo.upsert_activities(uid, [{**row, "distance_m": 9100.0}]) == 0  # mise à jour, pas de doublon
    assert repo.list_activities(uid, date(2026, 9, 1), 10)[0]["distance_m"] == 9100.0
    repo.touch_garmin(uid, None, "expiré")
    assert repo.get_garmin(uid)["last_error"] == "expiré"
    repo.delete_garmin(uid, True)
    assert repo.get_garmin(uid) is None and repo.list_activities(uid, date(2026, 9, 1), 10) == []


def test_move_session_keeps_the_original_day():
    from datetime import date

    repo = PostgresRepo(DSN)
    repo.migrate(Path(__file__).parent.parent / "db" / "migrations")
    uid = repo.create_user("move")
    repo.add_sessions(uid, [{"day": date(2026, 10, 12), "kind": "run_easy", "title": "Footing", "duration_min": 30, "details": {"zone": "z2"}, "rules": ["C1"], "notes": []}])
    sid = repo.list_sessions(uid, date(2026, 10, 1), None)[0]["id"]
    same = repo.move_session(uid, sid, date(2026, 10, 12))
    assert same["day"] == date(2026, 10, 12) and "moved_from" not in same["details"]
    moved = repo.move_session(uid, sid, date(2026, 10, 14))
    assert moved["day"] == date(2026, 10, 14) and moved["details"] == {"zone": "z2", "moved_from": "2026-10-12"}
    again = repo.move_session(uid, sid, date(2026, 10, 16))
    assert again["details"]["moved_from"] == "2026-10-12"  # le premier jour prévu est conservé
    assert repo.move_session(uid + 999, sid, date(2026, 10, 16)) is None
