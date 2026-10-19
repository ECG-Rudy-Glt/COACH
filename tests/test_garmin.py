from datetime import date, timedelta

import pytest
from cryptography.fernet import Fernet
from fastapi.testclient import TestClient

from app.garmin import crypto
from app.garmin.client import GarminAuthError, LoginResult, normalize
from app.main import app, get_repo
from app.repo import MemoryRepo

PW = "un-mot-de-passe-solide"
TODAY = date.today()


def act(i, days_ago, sport="run", km=8.0, minutes=50):
    d = TODAY - timedelta(days=days_ago)
    return {"garmin_id": str(i), "day": d, "started_at": __import__("datetime").datetime(d.year, d.month, d.day, 7, 30),
            "sport": sport, "type_key": "running", "name": "Sortie", "duration_s": minutes * 60, "distance_m": km * 1000,
            "elevation_m": 120.0, "avg_hr": 150, "max_hr": 175, "calories": 600, "training_load": 90.0}


class FakeGarmin:
    def __init__(self):
        self.mfa = False
        self.bad = False
        self.activities = [act(i, i * 3) for i in range(1, 12)]

    def start_login(self, email, password):
        if self.bad or password == "mauvais":
            raise GarminAuthError("refus")
        return LoginResult(mfa_handle=("h",)) if self.mfa else LoginResult(tokens="TOKEN-" + "x" * 600)

    def finish_mfa(self, handle, code):
        if code != "123456":
            raise GarminAuthError("code")
        return LoginResult(tokens="TOKEN-" + "y" * 600)

    def fetch_metrics(self, tokens, start, end, monthly_predictions):
        if getattr(self, "metrics_fail", False):
            raise RuntimeError("boom")
        return [{"day": end, "metric": "resting_hr", "value": 47.0}, {"day": end, "metric": "vo2max", "value": 52.0}], tokens

    def fetch_activities(self, tokens, start, end):
        if self.bad:
            raise GarminAuthError("expiré")
        return [a for a in self.activities if start <= a["day"] <= end], tokens


@pytest.fixture
def ctx(monkeypatch):
    from app.auth import reset_rate_limits

    monkeypatch.setenv("SECRETS_KEY", Fernet.generate_key().decode())
    reset_rate_limits()
    repo, fake = MemoryRepo(), FakeGarmin()
    app.dependency_overrides[get_repo] = lambda: repo
    old = app.state.garmin
    app.state.garmin = fake
    c = TestClient(app)
    uid = c.post("/auth/register", json={"name": "R", "email": "gm@example.org", "password": PW}).json()["id"]
    yield c, uid, repo, fake
    app.state.garmin = old
    app.dependency_overrides.clear()


def test_crypto_roundtrip_and_missing_key(monkeypatch):
    monkeypatch.setenv("SECRETS_KEY", Fernet.generate_key().decode())
    t = crypto.encrypt("secret-token")
    assert t != "secret-token" and crypto.decrypt(t) == "secret-token"
    monkeypatch.setenv("SECRETS_KEY", Fernet.generate_key().decode())  # autre clé : illisible
    with pytest.raises(crypto.NotConfigured):
        crypto.decrypt(t)
    monkeypatch.delenv("SECRETS_KEY")
    with pytest.raises(crypto.NotConfigured):
        crypto.encrypt("x")


def test_connect_without_mfa_stores_encrypted_token_never_the_password(ctx):
    c, uid, repo, _ = ctx
    r = c.post(f"/users/{uid}/garmin/connect", json={"email": "g@x.fr", "password": "super-secret-garmin"})
    assert r.status_code == 200 and r.json()["status"] == "connected" and r.json()["added"] > 0
    stored = repo.get_garmin(uid)
    assert "super-secret-garmin" not in str(stored) and "TOKEN-" not in stored["tokens_enc"]  # chiffré
    st = c.get(f"/users/{uid}/garmin").json()
    assert st["connected"] and st["email"] == "g@x.fr" and st["last_sync_at"] and len(st["recent"]) > 0


def test_connect_with_mfa_and_wrong_code(ctx):
    c, uid, repo, fake = ctx
    fake.mfa = True
    assert c.post(f"/users/{uid}/garmin/connect", json={"email": "g@x.fr", "password": "pw"}).json() == {"status": "mfa_required"}
    assert not c.get(f"/users/{uid}/garmin").json()["connected"]
    assert c.post(f"/users/{uid}/garmin/mfa", json={"code": "000000"}).status_code == 401
    assert c.post(f"/users/{uid}/garmin/mfa", json={"code": "123456"}).json()["status"] == "connected"
    assert c.get(f"/users/{uid}/garmin").json()["connected"]


def test_bad_credentials_and_isolation(ctx):
    c, uid, repo, _ = ctx
    r = c.post(f"/users/{uid}/garmin/connect", json={"email": "g@x.fr", "password": "mauvais"})
    assert r.status_code == 401 and "refusés" in r.json()["detail"]
    c.post("/auth/logout")
    other = c.post("/auth/register", json={"name": "E", "email": "e2@example.org", "password": PW}).json()["id"]
    assert c.get(f"/users/{uid}/garmin").status_code == 403
    assert not c.get(f"/users/{other}/garmin").json()["connected"]


def test_sync_is_idempotent_derives_volume_and_completes_sessions(ctx):
    c, uid, repo, fake = ctx
    repo.add_sessions(uid, [{"day": TODAY - timedelta(days=3), "kind": "run_easy", "title": "Footing", "duration_min": 45,
                             "details": {}, "rules": ["C1"], "notes": []}])
    r = c.post(f"/users/{uid}/garmin/connect", json={"email": "g@x.fr", "password": "pw"}).json()
    assert r["sessions_completed"] == 1
    again = c.post(f"/users/{uid}/garmin/sync").json()
    assert again["added"] == 0 and again["sessions_completed"] == 0  # pas de doublon
    done = [s for s in repo.list_sessions(uid, TODAY - timedelta(days=10), None) if s["status"] == "done"]
    assert done and done[0]["logged"]["source"] == "garmin"
    prof = c.get(f"/users/{uid}/profile").json()["facts"]
    assert prof["running.weekly_km_8w"] > 0  # volume mesuré remplace l'estimation


def test_measured_volume_replaces_overstated_declaration(ctx):
    c, uid, repo, fake = ctx
    c.post(f"/users/{uid}/answers", json={"question_id": "run.recent_volume", "value": 30})
    fake.activities = [act(i, i * 6, sport="bike", km=40, minutes=90) for i in range(1, 9)] + [act(99, 20, km=5, minutes=35)]
    c.post(f"/users/{uid}/garmin/connect", json={"email": "g@x.fr", "password": "pw"})
    km = c.get(f"/users/{uid}/profile").json()["facts"]["running.weekly_km_8w"]
    assert km < 2  # 5 km sur 8 semaines, pas les 30 km déclarés


def test_expired_token_asks_reconnect_and_disconnect_purges(ctx):
    c, uid, repo, fake = ctx
    c.post(f"/users/{uid}/garmin/connect", json={"email": "g@x.fr", "password": "pw"})
    fake.bad = True
    r = c.post(f"/users/{uid}/garmin/sync")
    assert r.status_code == 401 and "reconnectez" in r.json()["detail"]
    assert "reconnectez" in c.get(f"/users/{uid}/garmin").json()["last_error"]
    assert c.delete(f"/users/{uid}/garmin?purge=true").json() == {"ok": True}
    st = c.get(f"/users/{uid}/garmin").json()
    assert not st["connected"] and st["recent"] == []
    assert c.post(f"/users/{uid}/garmin/sync").status_code == 409


def test_two_years_history_backfill_prune_and_daily_window(ctx):
    c, uid, repo, fake = ctx
    fake.activities = [act(i, d) for i, d in enumerate([5, 40, 200, 500, 700, 760], 1)]
    r = c.post(f"/users/{uid}/garmin/connect", json={"email": "g@x.fr", "password": "pw"}).json()
    assert r["backfill"] is True and r["fetched"] == 5  # 760 jours dépasse la fenêtre de 2 ans
    assert c.get(f"/users/{uid}/garmin").json()["total_activities"] == 5
    fake.activities.append(act(50, 1))
    again = c.post(f"/users/{uid}/garmin/sync").json()
    assert again["backfill"] is False and again["fetched"] == 2 and again["added"] == 1  # fenêtre courte : 28 jours
    repo.upsert_activities(uid, [act(77, 800)])  # trop ancienne : supprimée à la synchro suivante
    c.post(f"/users/{uid}/garmin/sync")
    assert all(a["garmin_id"] != "77" for a in repo.list_activities(uid, TODAY - timedelta(days=1000), 100))


def test_coach_context_summarises_two_years(ctx):
    from app.coach import service

    c, uid, repo, fake = ctx
    fake.activities = [act(i, i * 9, sport="bike" if i % 2 else "run", km=30 if i % 2 else 8) for i in range(1, 60)]
    c.post(f"/users/{uid}/garmin/connect", json={"email": "g@x.fr", "password": "pw"})
    h = service.build_context(repo, uid, TODAY)["historique_garmin"]
    assert h["total_activites"] == 59 and len(h["semaines_recentes"]) == 12 and h["mois"]
    assert any("velo" in m and "course" in m for m in h["mois"].values())


def test_not_configured_server(ctx, monkeypatch):
    c, uid, _, _ = ctx
    monkeypatch.delenv("SECRETS_KEY")
    assert c.get(f"/users/{uid}/garmin").json()["configured"] is False
    assert c.post(f"/users/{uid}/garmin/connect", json={"email": "a@b.fr", "password": "x"}).status_code == 503


def test_normalize_activity():
    raw = {"activityId": 42, "startTimeLocal": "2026-10-04 07:31:00", "activityType": {"typeKey": "trail_running"},
           "activityName": "Trail", "duration": 3600.4, "distance": 10200.0, "elevationGain": 420.0, "averageHR": 151.0,
           "maxHR": 178, "calories": 700.0, "activityTrainingLoad": 120.5}
    n = normalize(raw)
    assert n["sport"] == "run" and n["day"] == date(2026, 10, 4) and n["avg_hr"] == 151 and n["duration_s"] == 3600
    assert normalize({"activityId": 1}) is None


def test_pair_up_prefers_closest_duration_and_never_reuses():
    from datetime import date

    from app.garmin.match import link_fields, pair_up
    d = date(2026, 10, 12)
    sess = [{"id": 1, "day": d, "kind": "strength_upper", "duration_min": 77, "status": "planned", "logged": None},
            {"id": 2, "day": d, "kind": "run_easy", "duration_min": 60, "status": "planned", "logged": None},
            {"id": 3, "day": d, "kind": "strength_crossfit", "duration_min": 40, "status": "planned", "logged": None}]
    acts = [{"garmin_id": "a", "day": d, "sport": "strength", "duration_s": 70 * 60, "distance_m": 0, "avg_hr": 116, "max_hr": 150, "calories": 400, "training_load": 85.4, "name": "Musculation"},
            {"garmin_id": "b", "day": d, "sport": "strength", "duration_s": 38 * 60, "distance_m": 0, "avg_hr": 150, "max_hr": 180, "calories": 380, "training_load": 90, "name": "HIIT"},
            {"garmin_id": "c", "day": d, "sport": "bike", "duration_s": 3000, "distance_m": 9000, "avg_hr": 120, "max_hr": 140, "calories": 200, "training_load": 20, "name": "Vélo"},
            {"garmin_id": "d", "day": d, "sport": "run", "duration_s": 120, "distance_m": 300, "avg_hr": 100, "max_hr": 110, "calories": 10, "training_load": 1, "name": "Marche"}]
    got = {s["id"]: a["garmin_id"] for s, a in pair_up(sess, acts)}
    assert got == {1: "a", 3: "b"}  # le vélo n'est pas planifié, l'activité de 2 min n'est pas une séance
    done = {**sess[0], "status": "done", "logged": {"note": "bien", "minutes": 75, "rpe": 7}}
    out = link_fields(done, acts[0])
    assert out["note"] == "bien" and out["minutes"] == 75 and out["avg_hr"] == 116 and out["training_load"] == 85 and "source" not in out
    assert pair_up([{**done, "logged": out}], acts) == []  # déjà reliée


def test_metrics_are_stored_on_sync_and_never_break_it(ctx):
    c, uid, repo, fake = ctx
    c.post(f"/users/{uid}/garmin/connect", json={"email": "a@b.fr", "password": "ok"})
    assert c.post(f"/users/{uid}/garmin/sync").status_code == 200
    assert {m["metric"] for m in repo.list_metrics(uid, None, date.today() - timedelta(days=5))} == {"resting_hr", "vo2max"}
    fake.metrics_fail = True
    assert c.post(f"/users/{uid}/garmin/sync").status_code == 200  # les mesures sont secondaires : la synchro des activités continue


def test_activity_one_day_late_still_completes_the_planned_session(ctx):
    c, uid, repo, fake = ctx
    repo.add_sessions(uid, [{"day": TODAY - timedelta(days=2), "kind": "run_long", "title": "Sortie longue", "duration_min": 25, "details": {},
                             "rules": ["C2"], "notes": []}])
    fake.activities = [act(1, 1, minutes=45), act(2, 1, sport="bike", km=2, minutes=8)]  # le vélo de 8 min est ignoré
    r = c.post(f"/users/{uid}/garmin/connect", json={"email": "g@x.fr", "password": "pw"}).json()
    assert r["sessions_completed"] == 1
    s = repo.list_sessions(uid, TODAY - timedelta(days=3), None)[0]
    assert s["status"] == "done" and s["logged"]["minutes"] == 45


def test_one_activity_completes_only_one_session_and_never_a_future_one(ctx):
    c, uid, repo, fake = ctx
    repo.add_sessions(uid, [
        {"day": TODAY - timedelta(days=2), "kind": "run_long", "title": "Longue", "duration_min": 25, "details": {}, "rules": ["C2"], "notes": []},
        {"day": TODAY + timedelta(days=1), "kind": "run_easy", "title": "Footing de demain", "duration_min": 25, "details": {}, "rules": ["C1"], "notes": []}])
    fake.activities = [act(1, 1, minutes=45)]  # hier : la veille de la sortie prévue il y a 2 jours est un jour trop tôt, demain est dans le futur
    r = c.post(f"/users/{uid}/garmin/connect", json={"email": "g@x.fr", "password": "pw"}).json()
    assert r["sessions_completed"] == 1
    st = {s["title"]: s["status"] for s in repo.list_sessions(uid, TODAY - timedelta(days=5), None)}
    assert st["Longue"] == "done" and st["Footing de demain"] == "planned"
    c.post(f"/users/{uid}/garmin/sync")  # idempotent : la même activité ne valide rien de plus
    assert {s["title"]: s["status"] for s in repo.list_sessions(uid, TODAY - timedelta(days=5), None)}["Footing de demain"] == "planned"
