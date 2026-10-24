"""Courbes d'une activité (règles ST25 à ST28) : parseurs FIT/TCX/GPX, aucune position GPS, API, isolation entre utilisateurs, suppression, détail Garmin à la demande."""
import base64
import json
import struct
from datetime import UTC, date, datetime, timedelta

import pytest
from cryptography.fernet import Fernet
from fastapi.testclient import TestClient
from test_activity_import import FIT_EPOCH, _crc16, _msg

from app.activity_import import streams as S
from app.auth import reset_rate_limits
from app.curves import zones as Z
from app.garmin.client import GarminAuthError, GarminUnavailable
from app.main import app, get_repo
from app.questionnaire.models import Fact
from app.repo import MemoryRepo

PW = "un-mot-de-passe-solide"
TODAY = date.today()
START = datetime(TODAY.year, TODAY.month, TODAY.day, 7, 30, tzinfo=UTC) - timedelta(days=1)
LAT, LON = 48.8566, 2.3522  # position synthétique : ne doit jamais ressortir


def make_fit(seconds: int = 1200, sport: int = 1, laps: bool = True) -> bytes:
    ts0 = int((START - FIT_EPOCH).total_seconds())
    rec = [(253, 4, 0x86, 0), (3, 1, 0x02, 0), (5, 4, 0x86, 0), (2, 2, 0x84, 0), (6, 2, 0x84, 0), (4, 1, 0x02, 0), (7, 2, 0x84, 0), (0, 4, 0x85, 0), (1, 4, 0x85, 0)]
    out = b""
    for i in range(seconds):
        lat = int(LAT * (2**31) / 180) + i
        lon = int(LON * (2**31) / 180) + i
        out += _msg(0, 20, rec, [ts0 + i, 120 + (i * 70) // seconds, int(3.2 * i * 100), int((100 + i / 20 + 500) * 5), 3200, 85, 200, lat & 0xFFFFFFFF, lon & 0xFFFFFFFF])
    if laps:
        lap = [(253, 4, 0x86, 0), (2, 4, 0x86, 0), (7, 4, 0x86, 0), (9, 4, 0x86, 0), (15, 1, 0x02, 0)]
        for k in range(2):
            out += _msg(2, 19, lap, [ts0 + (k + 1) * seconds // 2, ts0 + k * seconds // 2, seconds // 2 * 1000, int(3.2 * seconds / 2 * 100), 140 + 10 * k])
    ses = [(253, 4, 0x86, 0), (2, 4, 0x86, 0), (7, 4, 0x86, 0), (9, 4, 0x86, 0), (5, 1, 0x00, 0), (6, 1, 0x00, 0)]
    out += _msg(1, 18, ses, [ts0 + seconds, ts0, seconds * 1000, int(3.2 * seconds * 100), sport, 0])
    header = struct.pack("<BBHI4s", 14, 0x20, 2100, len(out), b".FIT")
    header += struct.pack("<H", _crc16(header))
    body = header + out
    return body + struct.pack("<H", _crc16(body))


def make_tcx(n: int = 120, run: bool = True, hr: bool = True) -> bytes:
    iso = lambda s: (START + timedelta(seconds=s)).strftime("%Y-%m-%dT%H:%M:%SZ")  # noqa: E731
    pts = ""
    for i in range(n):
        tpx = f"<Speed>{2.8 + (i % 5) / 10}</Speed><Watts>{180 + i}</Watts>" + ("<RunCadence>86</RunCadence>" if run else "")
        pts += (f"<Trackpoint><Time>{iso(i * 10)}</Time>"
                f"<Position><LatitudeDegrees>{LAT}</LatitudeDegrees><LongitudeDegrees>{LON}</LongitudeDegrees></Position>"
                f"<AltitudeMeters>{100 + i / 4}</AltitudeMeters><DistanceMeters>{i * 28}</DistanceMeters>"
                + (f"<HeartRateBpm><Value>{140 + i // 10}</Value></HeartRateBpm>" if hr else "") + ("" if run else "<Cadence>90</Cadence>")
                + f'<Extensions><TPX xmlns="http://www.garmin.com/xmlschemas/ActivityExtension/v2">{tpx}</TPX></Extensions></Trackpoint>')
    ns = "http://www.garmin.com/xmlschemas/TrainingCenterDatabase/v2"
    return (f'<?xml version="1.0"?><TrainingCenterDatabase xmlns="{ns}"><Activities><Activity Sport="{"Running" if run else "Biking"}"><Id>{iso(0)}</Id>'
            f'<Lap StartTime="{iso(0)}"><TotalTimeSeconds>{n * 10}</TotalTimeSeconds><DistanceMeters>{n * 28}</DistanceMeters>'
            f"<Track>{pts}</Track></Lap></Activity></Activities></TrainingCenterDatabase>").encode()


def make_gpx(n: int = 100) -> bytes:
    pts = "".join(f'<trkpt lat="{LAT + i * 0.0002}" lon="{LON}"><ele>{50 + i / 10}</ele><time>{(START + timedelta(seconds=i * 6)).strftime("%Y-%m-%dT%H:%M:%SZ")}</time></trkpt>' for i in range(n))
    return f'<?xml version="1.0"?><gpx version="1.1" xmlns="http://www.topografix.com/GPX/1/1"><trk><name>Sortie</name><trkseg>{pts}</trkseg></trk></gpx>'.encode()


def no_position(streams: dict) -> bool:
    text = json.dumps(streams).lower()
    return "lat" not in text and "lon" not in text and "position" not in text and str(LAT) not in text


# ---------- parseurs ----------

def test_fit_streams_are_downsampled_without_position():
    s = S.parse_streams(make_fit())
    assert s and 300 <= s["n"] <= 500 and s["n"] == len(s["t"]) == len(s["hr"]) == len(s["speed"]) == len(s["alt"]) == len(s["dist"])
    assert s["t"] == sorted(s["t"]) and s["duration_s"] >= 1190
    assert 118 <= s["hr"][0] <= 125 and s["hr"][-1] >= 185 and all(30 <= h <= 250 for h in s["hr"])
    assert s["cad"][0] == 170 and s["power"][0] == 200  # course : foulées d'un pied doublées en pas par minute
    assert all(abs(v - 3.2) < 0.05 for v in s["speed"])
    assert no_position(s)
    assert [k["dist_m"] for k in s["splits"]["km"]] == [1000, 1000, 1000, 837] and abs(s["splits"]["km"][0]["dur_s"] - 312) <= 2
    assert [lap["dur_s"] for lap in s["splits"]["laps"]] == [600, 600] and s["splits"]["laps"][1]["hr"] == 150


def test_short_series_are_kept_as_recorded_and_bike_cadence_is_not_doubled():
    s = S.parse_streams(make_fit(seconds=120, sport=2, laps=False))
    assert s["n"] == 120 and s["cad"][0] == 85 and s["splits"]["km"] == [] and s["splits"]["laps"] == []


def test_tcx_streams_extensions_and_missing_series():
    s = S.parse_streams(make_tcx())
    assert s["n"] == 120 and s["cad"][0] == 172 and s["power"][0] == 180 and no_position(s) and abs(s["speed"][0] - 2.8) < 0.01
    bike = S.parse_streams(make_tcx(run=False, hr=False))
    assert bike["hr"] is None and bike["cad"][0] == 90  # pas de FC dans le fichier : aucune courbe de FC (jamais des zéros)


def test_gpx_distance_and_speed_come_from_positions_which_are_forgotten():
    s = S.parse_streams(make_gpx())
    assert s["hr"] is None and s["cad"] is None and s["power"] is None
    assert s["dist"][-1] > 1500 and 3.0 < s["speed"][5] < 4.5 and no_position(s)


def test_garbage_and_unusable_files_give_none_never_raise():
    for raw in (b"", b"n'importe quoi", b"<gpx><trk></trk></gpx>", b"<?xml version='1.0'?><!DOCTYPE x [<!ENTITY a 'b'>]><gpx/>", make_fit(seconds=5), make_fit()[:200], make_gpx(n=3)):
        assert S.parse_streams(raw) is None


def test_outliers_are_dropped_not_zeroed_and_pauses_stay_gaps():
    base = [S._sample(START + timedelta(seconds=i), dist=i * 3, hr=300 if i == 5 else 140, speed=99 if i == 6 else 3, power=9000 if i == 7 else 100) for i in range(60)]
    s = S.build(base, [])
    assert s["hr"][5] is None and s["speed"][6] is None and s["power"][7] is None and s["hr"][4] == 140
    paused = [S._sample(START + timedelta(seconds=i if i < 100 else i + 3600), hr=140) for i in range(1000)]
    pts = S.downsample([{**p, "t": (p["ts"] - START).total_seconds()} for p in paused])
    gaps = [b["t"] - a["t"] for a, b in zip(pts, pts[1:], strict=False)]
    assert len(pts) <= S.MAX_POINTS and max(gaps) > 3000  # la pause n'est pas comblée par un faux point


# ---------- zones ----------

def test_zones_use_the_plan_bounds_and_ignore_gaps():
    assert Z.zone_edges(200) == [120, 150, 170, 184]
    assert [Z.zone_of(h, 200) for h in (100, 120, 149, 150, 170, 184, 199)] == [0, 1, 1, 2, 3, 4, 4]
    assert Z.time_in_zones([0, 10, 20, 30, 4000], [100, 130, 160, None, 190], 200) == [10, 10, 10, 0, 0]
    assert Z.zones_block({"hr": None, "t": []}, 190, "declared") is None and Z.zones_block({"hr": [150], "t": [0]}, None, None) is None


# ---------- API ----------

@pytest.fixture
def env(monkeypatch):
    monkeypatch.setenv("SECRETS_KEY", Fernet.generate_key().decode())
    reset_rate_limits()
    repo = MemoryRepo()
    app.dependency_overrides[get_repo] = lambda: repo
    c = TestClient(app)
    uid = c.post("/auth/register", json={"name": "R", "email": "cv@example.org", "password": PW}).json()["id"]
    yield c, repo, uid
    app.dependency_overrides.clear()


def import_file(c, uid, raw, name="a.fit"):
    r = c.post(f"/users/{uid}/activities/import", json={"files": [{"name": name, "data": base64.b64encode(raw).decode()}]})
    assert r.status_code == 200 and r.json()["imported"] == 1, r.text
    return next(a for a in c.app.dependency_overrides[get_repo]().list_activities(uid, TODAY - timedelta(days=5), 10))


def link_session(c, uid, act, kind="run_easy"):
    sid = c.post(f"/users/{uid}/plan/sessions", json={"day": act["day"].isoformat(), "kind": kind, "title": "Footing", "duration_min": 25}).json()["id"]
    assert c.post(f"/users/{uid}/plan/sessions/{sid}/link", json={"garmin_id": act["garmin_id"]}).status_code == 200
    return sid


def test_import_stores_curves_and_session_endpoint_returns_them(env):
    c, repo, uid = env
    act = import_file(c, uid, make_fit())
    sid = link_session(c, uid, act)
    d = c.get(f"/users/{uid}/plan/sessions/{sid}/curves").json()
    assert c.post(f"/users/{uid}/plan/sessions/{sid}/curves/fetch").json()["available"]  # courbes déjà en base : rien à télécharger, même sans compte Garmin
    assert d["available"] and 300 <= d["n"] <= 500 and d["source"] == "fit" and d["zones"] is None  # aucune FC max connue : pas de bande
    assert len(d["splits"]["km"]) == 4 and "lat" not in json.dumps(d).lower()
    assert d["summary"]["done"]["minutes"] == 20 and d["summary"]["done"]["pace_s_km"] == 312
    repo.add_facts(uid, [Fact(key="running.hr_max", value=190)])
    z = c.get(f"/users/{uid}/plan/sessions/{sid}/curves").json()["zones"]
    assert z["basis"] == "declared" and z["hr_max"] == 190 and sum(z["seconds"]) > 1100 and z["edges"] == [114, 142, 162, 175]


def test_summary_planned_vs_done_and_manual_session_has_no_planned(env):
    c, _, uid = env
    act = import_file(c, uid, make_fit())
    sid = link_session(c, uid, act)
    s = c.get(f"/users/{uid}/plan/sessions/{sid}/curves").json()["summary"]
    assert s["manual"] and s["planned"] is None and s["gap_minutes"] is None


def test_no_activity_and_no_streams_reasons(env):
    c, repo, uid = env
    sid = c.post(f"/users/{uid}/plan/sessions", json={"day": TODAY.isoformat(), "kind": "run_easy", "title": "C", "duration_min": 30}).json()["id"]
    assert c.get(f"/users/{uid}/plan/sessions/{sid}/curves").json() == {"available": False, "reason": "no_activity"}
    row = {"garmin_id": "777", "day": TODAY, "started_at": datetime.now(), "sport": "run", "type_key": "running", "name": "x", "duration_s": 1800, "distance_m": 5000.0, "elevation_m": None,
           "avg_hr": 150, "max_hr": 170, "calories": 300, "training_load": None}
    repo.upsert_activities(uid, [row])
    assert c.post(f"/users/{uid}/plan/sessions/{sid}/link", json={"garmin_id": "777"}).status_code == 200
    d = c.get(f"/users/{uid}/plan/sessions/{sid}/curves").json()
    assert d["available"] is False and d["reason"] == "no_streams" and d["can_fetch"] is False  # Garmin non connecté


def test_isolation_between_users_and_auth(env):
    c, repo, uid = env
    act = import_file(c, uid, make_fit())
    sid = link_session(c, uid, act)
    other = TestClient(app)
    oid = other.post("/auth/register", json={"name": "O", "email": "cv2@example.org", "password": PW}).json()["id"]
    assert other.get(f"/users/{uid}/plan/sessions/{sid}/curves").status_code == 403
    assert other.post(f"/users/{uid}/plan/sessions/{sid}/curves/fetch").status_code == 403
    assert other.get(f"/users/{oid}/plan/sessions/{sid}/curves").status_code == 404
    assert repo.get_streams(oid, act["garmin_id"]) is None and repo.save_streams(oid, act["garmin_id"], repo.get_streams(uid, act["garmin_id"])) is False  # pas de courbe sans activité à soi
    assert TestClient(app).get(f"/users/{uid}/plan/sessions/{sid}/curves").status_code == 401


def test_curves_are_deleted_with_the_activity(env):
    c, repo, uid = env
    act = import_file(c, uid, make_fit())
    gid = act["garmin_id"]
    assert repo.get_streams(uid, gid)
    repo.delete_garmin(uid, purge=True)
    assert repo.get_streams(uid, gid)  # un fichier importé reste après « supprimer mes activités Garmin »
    repo.prune_activities(uid, TODAY + timedelta(days=1))
    assert repo.get_streams(uid, gid) is None and repo.list_activities(uid, TODAY - timedelta(days=9), 10) == []


def test_import_still_works_without_curves(env):
    c, repo, uid = env
    act = import_file(c, uid, make_tcx(n=2, hr=False), "court.tcx")  # trop court pour des courbes : l'activité est tout de même importée
    assert repo.get_streams(uid, act["garmin_id"]) is None


# ---------- détail Garmin à la demande ----------

class FakeGateway:
    def __init__(self, raw: bytes | None = None, error: Exception | None = None):
        self.raw, self.error, self.calls = raw, error, 0

    def download_activity_tcx(self, tokens, garmin_id):
        self.calls += 1
        if self.error:
            raise self.error
        return self.raw, tokens


@pytest.fixture
def garmin(env):
    from app.garmin import crypto

    c, repo, uid = env
    repo.save_garmin(uid, "g@example.org", crypto.encrypt("TOKEN"))
    row = {"garmin_id": "4242", "day": TODAY - timedelta(days=1), "started_at": datetime(START.year, START.month, START.day, 7, 30), "sport": "run", "type_key": "running", "name": "x",
           "duration_s": 1200, "distance_m": 3840.0, "elevation_m": 20.0, "avg_hr": 150, "max_hr": 175, "calories": 300, "training_load": None}
    repo.upsert_activities(uid, [row])
    sid = c.post(f"/users/{uid}/plan/sessions", json={"day": row["day"].isoformat(), "kind": "run_easy", "title": "C", "duration_min": 20}).json()["id"]
    assert c.post(f"/users/{uid}/plan/sessions/{sid}/link", json={"garmin_id": "4242"}).status_code == 200
    old = app.state.garmin
    yield c, repo, uid, sid
    app.state.garmin = old


def test_garmin_fetch_on_demand_stores_curves_and_not_the_file(garmin):
    c, repo, uid, sid = garmin
    app.state.garmin = gw = FakeGateway(make_tcx())
    assert c.get(f"/users/{uid}/plan/sessions/{sid}/curves").json()["can_fetch"] is True
    d = c.post(f"/users/{uid}/plan/sessions/{sid}/curves/fetch").json()
    assert d["available"] and d["source"] == "garmin" and no_position(repo.get_streams(uid, "4242"))
    c.post(f"/users/{uid}/plan/sessions/{sid}/curves/fetch")
    assert gw.calls == 1  # déjà en base : pas de second appel à Garmin


@pytest.mark.parametrize(("error", "raw", "status"), [(GarminAuthError("x"), None, 401), (GarminUnavailable("x"), None, 502), (None, b"<pas du xml", 422)])
def test_garmin_fetch_errors(garmin, error, raw, status):
    c, repo, uid, sid = garmin
    app.state.garmin = FakeGateway(raw, error)
    assert c.post(f"/users/{uid}/plan/sessions/{sid}/curves/fetch").status_code == status
    assert repo.get_streams(uid, "4242") is None


def test_garmin_fetch_is_rate_limited(garmin):
    c, repo, uid, sid = garmin
    app.state.garmin = FakeGateway(None, GarminUnavailable("x"))
    codes = [c.post(f"/users/{uid}/plan/sessions/{sid}/curves/fetch").status_code for _ in range(14)]
    assert codes[:12] == [502] * 12 and codes[12] == 429  # appels Garmin limités par utilisateur
