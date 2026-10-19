import pytest
from fastapi.testclient import TestClient

from app.main import app, get_repo
from app.repo import MemoryRepo

PASSWORD = "un-mot-de-passe-solide"


@pytest.fixture
def client():
    from app.auth import reset_rate_limits

    reset_rate_limits()
    repo = MemoryRepo()
    app.dependency_overrides[get_repo] = lambda: repo
    yield TestClient(app)
    app.dependency_overrides.clear()


def new_user(client, email="rudy@example.org"):
    r = client.post("/auth/register", json={"name": "Rudy", "email": email, "password": PASSWORD})
    assert r.status_code == 201, r.text
    return r.json()["id"]


def test_requires_login_and_own_data_only(client):
    assert client.get("/users/1/profile").status_code == 401
    a = new_user(client, "a@example.org")
    assert client.get(f"/users/{a}/profile").status_code == 200
    client.post("/auth/logout")
    b = new_user(client, "b@example.org")  # se connecte en tant que b
    assert client.get(f"/users/{a}/profile").status_code == 403
    assert client.get(f"/users/{b}/profile").status_code == 200


def test_questionnaire_flow(client):
    uid = new_user(client)
    r = client.get(f"/users/{uid}/questions/next").json()
    assert r["questions"][0]["id"] == "goal.sports"

    r = client.post(f"/users/{uid}/answers", json={
        "question_id": "goal.sports", "value": ["running", "strength", "autre"],
        "other_text": "escalade"})
    assert r.status_code == 201
    assert r.json()["recorded"] == ["sports.practiced", "sports.practiced.other"]

    nxt = client.get(f"/users/{uid}/questions/next?n=10").json()["questions"]
    assert nxt[0]["id"] == "goal.primary"
    assert all("fact_key" not in q and "show_if" not in q for q in nxt)

    prof = client.get(f"/users/{uid}/profile").json()
    assert prof["facts"]["sports.practiced.other"] == "escalade"
    assert prof["answered"] == 1


def test_invalid_answer_rejected(client):
    uid = new_user(client)
    r = client.post(f"/users/{uid}/answers", json={
        "question_id": "goal.sports", "value": ["autre"]})
    assert r.status_code == 422
    r = client.post(f"/users/{uid}/answers", json={"question_id": "nope", "value": 1})
    assert r.status_code == 404


def test_latest_answer_replaces_in_profile(client):
    uid = new_user(client)
    for v in (80, 78):
        client.post(f"/users/{uid}/answers", json={"question_id": "body.weight", "value": v})
    assert client.get(f"/users/{uid}/profile").json()["facts"]["body.weight_kg"] == 78


def test_skip_anything_but_blocking(client):
    uid = new_user(client)
    # tout peut être passé, sauf la mention légale
    r = client.post(f"/users/{uid}/skip", json={"question_id": "he.disclaimer"})
    assert r.status_code == 422
    assert client.post(f"/users/{uid}/skip", json={"question_id": "goal.sports"}).status_code == 201
    r = client.post(f"/users/{uid}/skip", json={"question_id": "goal.target_weight"})
    assert r.status_code == 201
    prof = client.get(f"/users/{uid}/profile").json()
    assert "goal.target_weight_kg" not in prof["facts"] and prof["answered"] == 2


def test_bank_endpoint_hides_conditions(client):
    bank = client.get("/bank").json()
    assert len(bank) > 80 and all("show_if" not in q for q in bank)


def test_pwa_assets_served(client):
    assert "COACH" in client.get("/").text
    assert client.get("/manifest.webmanifest").json()["display"] == "standalone"
    assert client.get("/icons/apple-touch-icon.png").headers["content-type"] == "image/png"
    assert client.get("/sw.js").status_code == 200
    assert client.get("/healthz").json() == {"status": "ok"}  # l'API passe avant la PWA


def test_benchmarks_page(client):
    uid = new_user(client)
    assert client.get(f"/users/{uid}/benchmarks").json()["sections"] == []
    client.post(f"/users/{uid}/answers", json={
        "question_id": "goal.sports", "value": ["strength", "trail"]})
    page = client.get(f"/users/{uid}/benchmarks").json()
    titles = [s["title"] for s in page["sections"]]
    assert titles == ["Musculation", "Course à pied"]  # le trail ouvre la course
    r = client.put(f"/users/{uid}/benchmarks", json={"items": {
        "squat": {"pr": {"weight": 140, "reps": 3, "year": 2022},
                  "now": {"weight": 120, "reps": 5}},
        "run_10k": {"pr": {"time": "41:30"}, "now": {"time": "44:10"}},
        "dips": {"pr": {}, "now": {}},
    }})
    assert r.json() == {"saved": 3}
    page = client.get(f"/users/{uid}/benchmarks").json()
    assert page["values"]["squat"]["now"] == {"weight": 120, "reps": 5}
    assert page["values"]["run_10k"]["pr"]["time"] == "41:30"
    assert "dips" not in page["values"] and page["filled"] == 2
    facts = client.get(f"/users/{uid}/profile").json()["facts"]
    assert not any(k.startswith("bench.") for k in facts)


def test_benchmarks_validation(client):
    uid = new_user(client)
    bad = [("squat", {"pr": {"weight": -5}}), ("run_5k", {"pr": {"time": "abc"}}),
           ("pullups", {"now": {"reps": "x"}}), ("nope", {})]
    for bid, payload in bad:
        r = client.put(f"/users/{uid}/benchmarks", json={"items": {bid: payload}})
        assert r.status_code in (404, 422), bid


def test_benchmarks_hidden_for_declared_beginner():
    from fastapi.testclient import TestClient

    from app.main import app, get_repo
    from app.questionnaire.models import Fact
    from app.repo import MemoryRepo
    repo = MemoryRepo()
    app.dependency_overrides[get_repo] = lambda: repo
    try:
        c = TestClient(app)
        uid = c.post("/auth/register", json={"name": "Debutant", "email": "deb@example.org", "password": "un-mot-de-passe-solide"}).json()["id"]
        repo.add_facts(uid, [Fact(key="sports.practiced", value=["strength"], source="user"), Fact(key="history.sport_years", value=0, source="user")])
        assert c.get(f"/users/{uid}/benchmarks").json()["novice"] is True
        repo.add_facts(uid, [Fact(key="history.sport_years", value=5, source="user")])
        assert c.get(f"/users/{uid}/benchmarks").json()["novice"] is False
    finally:
        app.dependency_overrides.clear()
