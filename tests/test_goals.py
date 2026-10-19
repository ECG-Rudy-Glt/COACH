from datetime import date

import pytest
from fastapi.testclient import TestClient

from app.goals import conflicts
from app.main import app, get_repo
from app.repo import MemoryRepo

PW = "un-mot-de-passe-solide"


@pytest.fixture
def api():
    from app.auth import reset_rate_limits

    reset_rate_limits()
    repo = MemoryRepo()
    app.dependency_overrides[get_repo] = lambda: repo
    c = TestClient(app)
    uid = c.post("/auth/register", json={"name": "R", "email": "g@example.org", "password": PW}).json()["id"]
    yield c, uid
    app.dependency_overrides.clear()


def test_goal_lifecycle(api):
    c, uid = api
    r = c.post(f"/users/{uid}/goals", json={
        "title": "Trail 50 km", "kind": "event", "target_date": "2027-06-12", "priority": "principal",
        "details": {"distance_km": 50, "elevation_m": 2500}})
    assert r.status_code == 201 and r.json()["status"] == "active"
    gid = r.json()["id"]
    r = c.patch(f"/users/{uid}/goals/{gid}", json={"title": "Trail 55 km", "details": {"distance_km": 55}})
    assert r.json()["title"] == "Trail 55 km" and r.json()["details"] == {"distance_km": 55}
    assert c.patch(f"/users/{uid}/goals/{gid}", json={"clear_date": True}).json()["target_date"] is None
    assert c.patch(f"/users/{uid}/goals/{gid}", json={"status": "done"}).json()["status"] == "done"
    assert c.get(f"/users/{uid}/goals?status=active").json()["goals"] == []
    assert len(c.get(f"/users/{uid}/goals").json()["goals"]) == 1  # l'historique reste
    assert c.delete(f"/users/{uid}/goals/{gid}").status_code == 200
    assert c.delete(f"/users/{uid}/goals/{gid}").status_code == 404


def test_validation_and_isolation(api):
    c, uid = api
    assert c.post(f"/users/{uid}/goals", json={"title": ""}).status_code == 422
    assert c.post(f"/users/{uid}/goals", json={"title": "x", "details": {"evil": 1}}).status_code == 422
    assert c.post(f"/users/{uid}/goals", json={"title": "x", "target_date": "pas-une-date"}).status_code == 422
    gid = c.post(f"/users/{uid}/goals", json={"title": "Perdre 4 kg", "kind": "body"}).json()["id"]
    c.post("/auth/logout")
    other = c.post("/auth/register", json={"name": "E", "email": "e@example.org", "password": PW}).json()["id"]
    assert c.get(f"/users/{uid}/goals").status_code == 403
    assert c.patch(f"/users/{other}/goals/{gid}", json={"title": "volé"}).status_code == 404


def test_event_conflicts_within_six_weeks():
    g = [{"id": 1, "status": "active", "kind": "event", "target_date": date(2027, 6, 1)},
         {"id": 2, "status": "active", "kind": "event", "target_date": date(2027, 6, 20)},
         {"id": 3, "status": "active", "kind": "event", "target_date": date(2027, 10, 1)},
         {"id": 4, "status": "dropped", "kind": "event", "target_date": date(2027, 6, 5)}]
    assert conflicts(g) == [{"a": 1, "b": 2, "days": 19}]
