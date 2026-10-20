# ruff: noqa: F811  (la fixture ctx vient de test_garmin)
"""Rapprochement des activités Garmin et des séances : automatique, manuel, déplacement d'une séance."""
from datetime import date, timedelta

from test_garmin import TODAY, act, ctx  # noqa: F401

from app.garmin.match import auto_link, suggestions, unlink_fields


def session(day, kind="run_easy", title="Footing", minutes=30, **extra):
    return {"day": day, "kind": kind, "title": title, "duration_min": minutes, "details": {}, "rules": ["C1"], "notes": [], **extra}


def by_title(repo, uid):
    return {s["title"]: s for s in repo.list_sessions(uid, TODAY - timedelta(days=40), None)}


def test_a_session_logged_by_hand_is_linked_to_the_activity_of_the_same_day(ctx):
    """Le cas d'origine : séance saisie à la main (donc « faite »), activité synchronisée ensuite : elle ne reste plus « hors plan »."""
    c, uid, repo, fake = ctx
    repo.add_sessions(uid, [session(TODAY - timedelta(days=2), title="Footing saisi", minutes=40)])
    sid = repo.list_sessions(uid, TODAY - timedelta(days=5), None)[0]["id"]
    repo.update_session(uid, sid, "done", {"rpe": 6, "note": "bien", "minutes": 38})
    repo.upsert_activities(uid, [act(7, 2, minutes=41)])
    assert auto_link(repo, uid, TODAY) == 1
    s = by_title(repo, uid)["Footing saisi"]
    assert s["status"] == "done" and s["logged"]["garmin_id"] == "7" and s["logged"]["avg_hr"] == 150
    assert s["logged"]["rpe"] == 6 and s["logged"]["minutes"] == 38 and "source" not in s["logged"]  # la saisie de l'utilisateur est conservée
    assert auto_link(repo, uid, TODAY) == 0  # idempotent


def test_planned_session_of_the_same_day_is_completed_and_other_days_are_left_alone(ctx):
    c, uid, repo, fake = ctx
    repo.add_sessions(uid, [session(TODAY - timedelta(days=3), title="Lundi"), session(TODAY - timedelta(days=6), title="Autre jour")])
    repo.upsert_activities(uid, [act(1, 3, minutes=30)])
    assert auto_link(repo, uid, TODAY) == 1
    got = by_title(repo, uid)
    assert got["Lundi"]["status"] == "done" and got["Lundi"]["logged"]["source"] == "garmin"
    assert got["Autre jour"]["status"] == "planned"


def test_week_view_lists_off_plan_activities_with_suggestions(ctx):
    c, uid, repo, fake = ctx
    monday = TODAY - timedelta(days=TODAY.weekday())
    repo.add_sessions(uid, [session(monday, title="Prévu lundi", minutes=45), session(monday + timedelta(days=1), "strength_upper", "Muscu", 60)])
    d = monday + timedelta(days=2)
    repo.upsert_activities(uid, [act(9, (TODAY - d).days, minutes=44)])
    week = c.get(f"/users/{uid}/plan?week={monday.isoformat()}").json()
    (a,) = week["activities"]
    assert a["garmin_id"] == "9" and a["suggestions"][0]["title"] == "Prévu lundi"  # le même sport, le plus proche en jours puis en durée
    assert all(s["title"] != "Muscu" for s in a["suggestions"])  # la musculation n'est pas un footing


def test_manual_link_moves_the_session_to_the_day_it_was_really_done(ctx):
    c, uid, repo, fake = ctx
    monday = TODAY - timedelta(days=TODAY.weekday())
    repo.add_sessions(uid, [session(monday - timedelta(days=7), title="Footing prévu", minutes=45)])
    sid = repo.list_sessions(uid, monday - timedelta(days=8), None)[0]["id"]
    done_day = TODAY - timedelta(days=1)
    repo.upsert_activities(uid, [act(5, 1, minutes=47)])
    r = c.post(f"/users/{uid}/plan/sessions/{sid}/link", json={"garmin_id": "5"})
    assert r.status_code == 200, r.text
    s = repo.list_sessions(uid, monday - timedelta(days=8), None)[0]
    assert s["status"] == "done" and s["day"] == done_day and s["details"]["moved_from"] == (monday - timedelta(days=7)).isoformat()
    assert s["logged"]["garmin_id"] == "5" and s["logged"]["minutes"] == 47
    # sans déplacement, et une activité déjà prise n'est pas reprise
    repo.add_sessions(uid, [session(TODAY, title="Autre")])
    other = by_title(repo, uid)["Autre"]["id"]
    assert c.post(f"/users/{uid}/plan/sessions/{other}/link", json={"garmin_id": "5"}).status_code == 409
    assert c.post(f"/users/{uid}/plan/sessions/{other}/link", json={"garmin_id": "inconnue"}).status_code == 404
    assert c.post(f"/users/{uid}/plan/sessions/9999/link", json={"garmin_id": "5"}).status_code == 404


def test_unlink_keeps_what_the_user_typed(ctx):
    c, uid, repo, fake = ctx
    repo.add_sessions(uid, [session(TODAY - timedelta(days=1), title="Footing")])
    sid = repo.list_sessions(uid, TODAY - timedelta(days=3), None)[0]["id"]
    repo.upsert_activities(uid, [act(3, 1, minutes=30)])
    repo.update_session(uid, sid, "done", {"rpe": 5, "note": "ok"})
    assert c.post(f"/users/{uid}/plan/sessions/{sid}/link", json={"garmin_id": "3", "move": False}).status_code == 200
    r = c.delete(f"/users/{uid}/plan/sessions/{sid}/link")
    assert r.status_code == 200 and r.json()["logged"] == {"rpe": 5, "note": "ok", "minutes": 30}
    assert c.delete(f"/users/{uid}/plan/sessions/{sid}/link").status_code == 404
    assert unlink_fields({"source": "garmin", "garmin_id": "1", "rpe": 5}) == {"rpe": 5}


def test_reschedule_a_planned_session_with_warnings_and_limits(ctx):
    c, uid, repo, fake = ctx
    base = TODAY + timedelta(days=3)
    repo.add_sessions(uid, [session(base, "run_long", "Longue", 90), session(base + timedelta(days=3), "strength_lower", "Jambes", 60)])
    ids = {s["title"]: s["id"] for s in repo.list_sessions(uid, TODAY, None)}
    r = c.patch(f"/users/{uid}/plan/sessions/{ids['Jambes']}/move", json={"day": (base + timedelta(days=1)).isoformat()})
    assert r.status_code == 200
    body = r.json()
    assert body["session"]["day"] == (base + timedelta(days=1)).isoformat() and body["session"]["details"]["moved_from"] == (base + timedelta(days=3)).isoformat()
    assert any("G5" in w for w in body["warnings"]) and any("I1" in w for w in body["warnings"])
    ok = c.patch(f"/users/{uid}/plan/sessions/{ids['Jambes']}/move", json={"day": (base + timedelta(days=5)).isoformat()}).json()
    assert ok["warnings"] == [] and ok["session"]["details"]["moved_from"] == (base + timedelta(days=3)).isoformat()  # le jour d'origine est gardé
    bad = c.patch(f"/users/{uid}/plan/sessions/{ids['Longue']}/move", json={"day": (TODAY - timedelta(days=1)).isoformat()})
    assert bad.status_code == 422  # une séance à venir ne revient pas dans le passé
    assert c.patch(f"/users/{uid}/plan/sessions/{ids['Longue']}/move", json={"day": (TODAY + timedelta(days=400)).isoformat()}).status_code == 422
    assert c.patch(f"/users/{uid}/plan/sessions/9999/move", json={"day": TODAY.isoformat()}).status_code == 404
    repo.update_session(uid, ids["Longue"], "done", {})
    assert c.patch(f"/users/{uid}/plan/sessions/{ids['Longue']}/move", json={"day": (TODAY + timedelta(days=1)).isoformat()}).status_code == 422
    assert c.patch(f"/users/{uid}/plan/sessions/{ids['Longue']}/move", json={"day": (TODAY - timedelta(days=2)).isoformat()}).status_code == 200


def test_match_endpoint_and_isolation(ctx):
    c, uid, repo, fake = ctx
    repo.add_sessions(uid, [session(TODAY - timedelta(days=1), title="Hier")])
    repo.upsert_activities(uid, [act(4, 1, minutes=30)])
    assert c.post(f"/users/{uid}/plan/match").json() == {"linked": 1}
    assert c.post(f"/users/{uid}/plan/match").json() == {"linked": 0}
    assert c.post(f"/users/{uid + 1}/plan/match").status_code in (401, 403)


def test_suggestions_ignore_linked_skipped_and_far_sessions():
    d = date(2026, 10, 14)
    a = {"garmin_id": "x", "day": d, "sport": "run", "duration_s": 3000}
    sess = [{"id": 1, "day": d - timedelta(days=1), "kind": "run_easy", "title": "A", "status": "planned", "duration_min": 50, "logged": None},
            {"id": 2, "day": d, "kind": "run_long", "title": "B", "status": "planned", "duration_min": 90, "logged": None},
            {"id": 3, "day": d, "kind": "run_easy", "title": "C", "status": "skipped", "duration_min": 50, "logged": None},
            {"id": 4, "day": d, "kind": "run_easy", "title": "D", "status": "done", "duration_min": 50, "logged": {"garmin_id": "y"}},
            {"id": 5, "day": d - timedelta(days=5), "kind": "run_easy", "title": "E", "status": "planned", "duration_min": 50, "logged": None}]
    assert [s["title"] for s in suggestions(a, sess)] == ["B", "A"]  # le même jour d'abord
