import pytest
from fastapi.testclient import TestClient

from app.exercises import api as ex_api
from app.exercises.models import Exercise, Media
from app.exercises.sources import free_exercise, merge, norm_key, wger_exercise
from app.main import app, get_repo
from app.repo import MemoryRepo

LICENSES = {2: ("CC-BY-SA 4", "https://creativecommons.org/licenses/by-sa/4.0/")}
WGER = {
    "id": 12, "category": {"id": 9, "name": "Legs"},
    "muscles": [{"name": "Quadriceps femoris", "name_en": "Quads"}],
    "muscles_secondary": [{"name": "Gluteus maximus", "name_en": "Glutes"}, {"name": "Soleus", "name_en": ""}],
    "equipment": [{"id": 1, "name": "Barbell"}], "license": {"short_name": "CC-BY-SA 3", "url": "https://x/3"},
    "license_author": "flori",
    "images": [{"image": "https://wger.de/media/a.webp", "thumbnails": {"medium": "https://wger.de/media/a.png"},
                "is_main": True, "license": 2, "license_author": ""}],
    "videos": [{"video": "https://wger.de/media/v.MOV", "license": 2, "license_author": "Goulart"}],
    "translations": [
        {"language": "2", "name": "Back Squat", "description": "<p>Stand.</p>", "description_source": ""},
        {"language": "12", "name": "Squat arrière", "description": "<p>Placez la barre.<br>Descendez.</p>",
         "description_source": ""},
    ],
}
FREE = {"id": "Back_Squat", "name": "Back-Squat", "category": "strength", "equipment": "barbell",
        "level": "intermediate", "primaryMuscles": ["quadriceps"], "secondaryMuscles": ["glutes"],
        "instructions": ["Stand.", "Squat."], "images": ["Back_Squat/0.jpg", "Back_Squat/1.jpg"]}


def test_wger_transform():
    e = wger_exercise(WGER, LICENSES)
    assert e.name == "Squat arrière" and e.name_en == "Back Squat" and e.instructions_lang == "fr"
    assert e.muscles_primary == ["quadriceps"] and e.muscles_secondary == ["glutes", "calves"]
    assert e.equipment == ["barbell"] and e.region == "jambes"
    assert "Placez la barre." in e.instructions and "<" not in e.instructions
    img = next(m for m in e.media if m.kind == "image")
    assert img.license == "CC-BY-SA 4" and img.author == "flori"  # auteur de l'exercice à défaut
    assert next(m for m in e.media if m.kind == "video").author == "Goulart"


def test_wger_without_fr_or_en_is_skipped():
    assert wger_exercise({**WGER, "translations": [{"language": "1", "name": "Kniebeuge"}]}, LICENSES) is None


def test_free_transform_and_merge_dedupes_by_english_name():
    f = free_exercise(FREE)
    assert f.license.startswith("Unlicense") and len(f.media) == 2 and f.media[0].is_main
    assert f.media[0].url.endswith("exercises/Back_Squat/0.jpg") and f.instructions.startswith("1. Stand.")
    w = wger_exercise(WGER, LICENSES)
    merged = merge([w], [f, free_exercise({**FREE, "id": "Other", "name": "Other move"})], [])
    assert len(merged) == 2  # « Back-Squat » fusionné dans « Back Squat »
    assert merged[0].sources == ["wger", "free-exercise-db"] and len(merged[0].media) == 4
    assert norm_key("Back-Squat") == norm_key("back squat")


@pytest.fixture
def lib():
    repo = MemoryRepo()
    repo.replace_exercises([
        Exercise(source="c", source_id="1", name="Squat arrière", name_en="Back Squat", kind="strength",
                 muscles_primary=["quadriceps"], equipment=["barbell"], license="X",
                 media=[Media(kind="image", url="https://wger.de/media/a.webp", license="CC-BY-SA 4", author="flori")]),
        Exercise(source="c", source_id="2", name="Chat-vache", kind="mobility", muscles_primary=["middle back"],
                 equipment=["bodyweight"], license="Original"),
    ])
    app.dependency_overrides[get_repo] = lambda: repo
    c = TestClient(app)
    from app.auth import reset_rate_limits
    reset_rate_limits()
    c.post("/auth/register", json={"name": "R", "email": "r@example.org", "password": "un-mot-de-passe-solide"})
    yield c
    app.dependency_overrides.clear()


def test_library_requires_login():
    app.dependency_overrides[get_repo] = lambda: MemoryRepo()
    try:
        assert TestClient(app).get("/exercises").status_code == 401
    finally:
        app.dependency_overrides.clear()


def test_search_filters_and_order(lib):
    r = lib.get("/exercises").json()
    assert r["total"] == 2 and r["items"][0]["name"] == "Squat arrière"  # avec image d'abord
    assert r["items"][0]["thumb"] == 1 and r["items"][1]["thumb"] is None
    assert lib.get("/exercises?q=back").json()["total"] == 1  # nom anglais
    assert lib.get("/exercises?muscle=quadriceps").json()["total"] == 1
    assert lib.get("/exercises?equipment=bodyweight&kind=mobility").json()["total"] == 1
    assert lib.get("/exercises?kind=hyrox").json()["total"] == 0
    assert "quadriceps" in lib.get("/exercises/meta").json()["muscles"]


def test_detail_exposes_attribution(lib):
    d = lib.get("/exercises/1").json()
    assert d["license"] == "X" and d["media"][0]["author"] == "flori" and "url" not in d["media"][0]
    assert lib.get("/exercises/99").status_code == 404


def test_media_cached_and_host_checked(lib, monkeypatch, tmp_path):
    monkeypatch.setattr(ex_api, "MEDIA_DIR", tmp_path)
    calls = []
    monkeypatch.setattr(ex_api, "_fetch_image", lambda url: calls.append(url) or b"IMG")
    r = lib.get("/media/1")
    assert r.status_code == 200 and r.content == b"IMG" and r.headers["content-type"] == "image/webp"
    lib.get("/media/1")
    assert len(calls) == 1  # deuxième lecture depuis le cache
    assert lib.get("/media/99").status_code == 404


def test_fetch_refuses_foreign_hosts():
    from fastapi import HTTPException
    for url in ("https://evil.example/a.png", "http://wger.de/a.png", "file:///etc/passwd"):
        with pytest.raises(HTTPException):
            ex_api._fetch_image(url)
