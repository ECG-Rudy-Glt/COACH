"""Muscles travaillés (règles ST21 à ST24) : table de correspondance, séries pondérées, déséquilibres, API et isolation."""
import re
from datetime import date, timedelta
from pathlib import Path

import pytest
import yaml
from fastapi.testclient import TestClient

from app.auth import reset_rate_limits
from app.exercises.labels import MUSCLE_FR, WGER_MUSCLE
from app.exercises.models import Exercise
from app.main import app, get_repo
from app.muscles import groups as G
from app.plan.strength import PATTERNS
from app.repo import MemoryRepo

ROOT = Path(__file__).resolve().parent.parent
PW = "un-mot-de-passe-solide"
TODAY = date.today()


def ex(name, primary, secondary=()):
    return Exercise(source="t", source_id=name, name=name, muscles_primary=list(primary), muscles_secondary=list(secondary), license="x")


LIB = [ex("Bench Press", ["chest"], ["triceps", "shoulders"]), ex("Barbell Curl", ["biceps"], ["forearms"]), ex("Seated Row", ["middle back", "lats"], ["biceps"]),
       ex("Squat", ["quadriceps"], ["glutes", "hamstrings", "lower back"]), ex("Plank", ["abdominals"])]


@pytest.fixture
def env():
    reset_rate_limits()
    repo = MemoryRepo()
    repo.replace_exercises(LIB)
    app.dependency_overrides[get_repo] = lambda: repo
    c = TestClient(app)
    uid = c.post("/auth/register", json={"name": "R", "email": "mu@example.org", "password": PW}).json()["id"]
    yield c, repo, uid
    app.dependency_overrides.clear()


def add(c, uid, exercises, kind="strength_upper", day=TODAY):
    r = c.post(f"/users/{uid}/plan/sessions", json={"day": day.isoformat(), "kind": kind, "title": "S", "duration_min": 50, "logged": {"exercises": exercises}})
    assert r.status_code == 201, r.text
    return r.json()["id"]


def sets(n, kg=50, reps=8):
    return [{"kg": kg, "reps": reps} for _ in range(n)]


def test_every_library_muscle_is_mapped_to_a_drawn_group():
    custom = yaml.safe_load((ROOT / "data" / "custom_exercises.yaml").read_text(encoding="utf-8"))
    names = set(MUSCLE_FR) | set(WGER_MUSCLE.values()) | {m for e in custom for m in e.get("muscles_primary", []) + e.get("muscles_secondary", [])}
    assert names - set(G.MUSCLE_TO_GROUP) == set(), "un muscle de la bibliothèque n'a pas de groupe dans le schéma (app/muscles/groups.py)"
    assert set(G.MUSCLE_TO_GROUP.values()) == set(G.GROUPS) and len(G.GROUPS) == 15
    js = (ROOT / "app" / "static" / "stats.js").read_text(encoding="utf-8")
    body = js[js.index("const BODY = {"): js.index("const BODY_FILL")]
    assert set(re.findall(r"\b([a-z_]+): \[\"M", body)) == set(G.GROUPS), "chaque groupe doit être dessiné (face ou dos)"


def test_weighting_primary_one_secondary_half_and_no_double_count():
    assert G.muscles_of(["chest"], ["chest", "triceps"]) == ({"chest"}, {"triceps"})
    repo = MemoryRepo()
    repo.replace_exercises(LIB)
    resolve = G.Resolver(repo, PATTERNS)
    w, p, n, unknown = G.session_volume({"exercises": [{"name": "bench press", "sets": sets(4) + [{}]}, {"name": "Mystère", "sets": sets(2)}, {"name": "Squat", "sets": []}]}, resolve)
    assert n == 4 and unknown == ["Mystère"]  # une série vide ne compte pas ; un nom inconnu n'est pas deviné
    assert w == {"chest": 4, "triceps": 2.0, "shoulders": 2.0} and p == {"chest": 4}


def test_pattern_fallback_uses_the_engine_primary_muscle_only():
    resolve = G.Resolver(MemoryRepo(), PATTERNS)
    w, _, n, unknown = G.session_volume({"exercises": [{"name": "h_pull", "sets": sets(3)}]}, resolve)
    assert w == {"middle_back": 3} and n == 3 and not unknown


def test_balance_flags_need_enough_sets_and_are_soft():
    assert G.balance({"chest": 3, "shoulders": 2})["flags"] == []  # moins de 8 séries pondérées : rien n'est signalé
    b = G.balance({"chest": 8, "shoulders": 4, "lats": 2})
    assert "push_heavy" in b["flags"] and "legs_low" in b["flags"] and "core_low" in b["flags"] and b["ratio"] == 6.0
    ok = G.balance({"chest": 4, "lats": 4, "quadriceps": 4, "abs": 2, "calves": 2})
    assert ok["flags"] == [] and ok["families"]["legs"] == 6.0
    assert G.balance({"lats": 10})["flags"][0] == "pull_heavy"


def test_session_endpoint_strength_done(env):
    c, _, uid = env
    sid = add(c, uid, [{"name": "Bench Press", "sets": sets(3)}, {"name": "Barbell Curl", "sets": sets(2)}])
    d = c.get(f"/users/{uid}/plan/sessions/{sid}/muscles").json()
    rows = {r["group"]: r for r in d["rows"]}
    assert d["supported"] and len(d["rows"]) == 15 and d["sets_counted"] == 5
    assert rows["chest"]["level"] == 2 and rows["triceps"]["level"] == 1 and rows["triceps"]["sets"] == 1.5 and rows["calves"]["level"] == 0
    assert d["weights"] == {"primary": 1.0, "secondary": 0.5}


def test_session_endpoint_has_no_diagram_for_endurance_and_planned(env):
    c, _, uid = env
    run = c.post(f"/users/{uid}/plan/sessions", json={"day": TODAY.isoformat(), "kind": "run_easy", "title": "C", "duration_min": 40}).json()["id"]
    assert c.get(f"/users/{uid}/plan/sessions/{run}/muscles").json() == {"supported": False, "reason": "no_diagram"}
    bike = c.post(f"/users/{uid}/plan/sessions", json={"day": TODAY.isoformat(), "kind": "sport_bike", "title": "V", "duration_min": 60}).json()["id"]
    assert c.get(f"/users/{uid}/plan/sessions/{bike}/muscles").json()["reason"] == "no_diagram"
    assert c.get(f"/users/{uid}/plan/sessions/99999/muscles").status_code == 404


def test_planned_strength_session_gives_not_done(env):
    c, repo, uid = env
    repo.add_sessions(uid, [{"day": TODAY, "kind": "strength_upper", "title": "S", "duration_min": 50, "details": {}, "rules": [], "notes": []}])
    sid = repo.list_sessions(uid, TODAY, TODAY + timedelta(days=1))[0]["id"]
    assert c.get(f"/users/{uid}/plan/sessions/{sid}/muscles").json() == {"supported": False, "reason": "not_done"}


def test_isolation_and_auth(env):
    c, _, uid = env
    sid = add(c, uid, [{"name": "Bench Press", "sets": sets(3)}])
    other = TestClient(app)
    oid = other.post("/auth/register", json={"name": "O", "email": "mu2@example.org", "password": PW}).json()["id"]
    assert other.get(f"/users/{uid}/plan/sessions/{sid}/muscles").status_code == 403
    assert other.get(f"/users/{uid}/stats/muscles").status_code == 403
    assert other.get(f"/users/{oid}/plan/sessions/{sid}/muscles").status_code == 404  # la séance d'un autre n'est pas visible
    assert other.get(f"/users/{oid}/stats/muscles").json()["sessions"] == 0
    assert TestClient(app).get(f"/users/{uid}/stats/muscles").status_code == 401


def test_week_view_sums_sessions_and_ignores_other_weeks_and_endurance(env):
    c, _, uid = env
    monday = G.monday(TODAY)
    add(c, uid, [{"name": "Bench Press", "sets": sets(3)}], day=monday if monday <= TODAY else TODAY)
    add(c, uid, [{"name": "Seated Row", "sets": sets(4)}, {"name": "Inconnu", "sets": sets(1)}])
    add(c, uid, [{"name": "Bench Press", "sets": sets(5)}], day=TODAY - timedelta(days=14))
    c.post(f"/users/{uid}/plan/sessions", json={"day": TODAY.isoformat(), "kind": "run_easy", "title": "C", "duration_min": 40, "logged": {"exercises": [{"name": "Bench Press", "sets": sets(9)}]}})
    d = c.get(f"/users/{uid}/stats/muscles").json()
    rows = {r["group"]: r for r in d["rows"]}
    assert d["week_start"] == monday.isoformat() and d["current"] and d["sessions"] == 2
    assert rows["chest"]["sets"] == 3 and rows["lats"]["sets"] == 4 and rows["biceps"]["sets"] == 2 and d["unknown"] == ["Inconnu"]
    old = c.get(f"/users/{uid}/stats/muscles", params={"week": (TODAY - timedelta(days=14)).isoformat()}).json()
    assert old["sessions"] == 1 and not old["current"] and {r["group"]: r for r in old["rows"]}["chest"]["sets"] == 5
    assert c.get(f"/users/{uid}/stats/muscles", params={"week": "2001-01-01"}).status_code == 422
    assert c.get(f"/users/{uid}/stats/muscles", params={"week": "pas-une-date"}).status_code == 422
