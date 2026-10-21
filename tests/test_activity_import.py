"""Import d'activités FIT / TCX / GPX : lecture, déduplication, rejet des fichiers corrompus, isolation, limites."""
import base64
import struct
from datetime import UTC, date, datetime, timedelta

import pytest
from fastapi.testclient import TestClient

from app.activity_import.parse import ImportRejected, is_duplicate, map_sport, parse_activity
from app.main import app, get_repo
from app.repo import MemoryRepo

PW = "un-mot-de-passe-solide"
TODAY = date.today()
START = datetime(TODAY.year, TODAY.month, TODAY.day, 7, 30, tzinfo=UTC) - timedelta(days=1)
FIT_EPOCH = datetime(1989, 12, 31, tzinfo=UTC)


# ---------- fabrique de fichiers d'essai (aucune donnée réelle) ----------

def _crc16(data: bytes) -> int:
    table = [0x0000, 0xCC01, 0xD801, 0x1400, 0xF001, 0x3C00, 0x2800, 0xE401, 0xA001, 0x6C00, 0x7800, 0xB401, 0x5000, 0x9C01, 0x8801, 0x4400]
    crc = 0
    for b in data:
        crc = ((crc >> 4) & 0x0FFF) ^ table[crc & 0xF] ^ table[b & 0xF]
        crc = ((crc >> 4) & 0x0FFF) ^ table[crc & 0xF] ^ table[(b >> 4) & 0xF]
    return crc & 0xFFFF


def _msg(local: int, global_num: int, fields: list[tuple[int, int, int, int]], values: list[int]) -> bytes:
    """Définition + données d'un message FIT ; champs = (numéro, taille, type de base, ...) en petit-boutiquien."""
    d = bytes([0x40 | local, 0, 0]) + struct.pack("<HB", global_num, len(fields)) + b"".join(bytes([n, size, bt]) for n, size, bt, _ in fields)
    body = bytes([local]) + b"".join(v.to_bytes(size, "little") for (_, size, _, _), v in zip(fields, values, strict=True))
    return d + body


def make_fit(start: datetime = START, minutes: int = 45, km: float = 8.0, hr: bool = True, sport: int = 1, sub_sport: int = 0) -> bytes:
    ts = int((start - FIT_EPOCH).total_seconds())
    rec = [(253, 4, 0x86, 0), (3, 1, 0x02, 0), (5, 4, 0x86, 0)]
    out = b""
    for i in range(3):
        out += _msg(0, 20, rec, [ts + i * 60, 150 + i if hr else 0xFF, int(km * 100 * i)])
    ses = [(253, 4, 0x86, 0), (2, 4, 0x86, 0), (7, 4, 0x86, 0), (9, 4, 0x86, 0), (11, 2, 0x84, 0), (16, 1, 0x02, 0), (17, 1, 0x02, 0), (22, 2, 0x84, 0),
           (5, 1, 0x00, 0), (6, 1, 0x00, 0)]
    out += _msg(1, 18, ses, [ts + minutes * 60, ts, minutes * 60 * 1000, int(km * 1000 * 100), 480, 152 if hr else 0xFF, 171 if hr else 0xFF, 85, sport, sub_sport])
    header = struct.pack("<BBHI4s", 14, 0x20, 2100, len(out), b".FIT")
    header += struct.pack("<H", _crc16(header))
    body = header + out
    return body + struct.pack("<H", _crc16(body))


def make_tcx(start: datetime = START, minutes: int = 45, km: float = 8.0, hr: bool = True, sport: str = "Running") -> bytes:
    hr_xml = '<AverageHeartRateBpm><Value>150</Value></AverageHeartRateBpm><MaximumHeartRateBpm><Value>172</Value></MaximumHeartRateBpm>' if hr else ""
    pt = lambda m, alt: (f'<Trackpoint><Time>{(start + timedelta(minutes=m)).strftime("%Y-%m-%dT%H:%M:%SZ")}</Time><AltitudeMeters>{alt}</AltitudeMeters>'  # noqa: E731
                         + (f"<HeartRateBpm><Value>{140 + m}</Value></HeartRateBpm>" if hr else "") + "</Trackpoint>")
    return (f'<?xml version="1.0" encoding="UTF-8"?><TrainingCenterDatabase xmlns="http://www.garmin.com/xmlschemas/TrainingCenterDatabase/v2">'
            f'<Activities><Activity Sport="{sport}"><Id>{start.strftime("%Y-%m-%dT%H:%M:%SZ")}</Id>'
            f'<Lap StartTime="{start.strftime("%Y-%m-%dT%H:%M:%SZ")}"><TotalTimeSeconds>{minutes * 60}</TotalTimeSeconds><DistanceMeters>{km * 1000}</DistanceMeters>'
            f'<Calories>480</Calories>{hr_xml}<Track>{pt(0, 100)}{pt(1, 110)}{pt(2, 125)}</Track></Lap></Activity></Activities></TrainingCenterDatabase>').encode()


def make_gpx(start: datetime = START, minutes: int = 30, timed: bool = True, hr: bool = True) -> bytes:
    pts = ""
    for i in range(4):
        t = f"<time>{(start + timedelta(minutes=i * minutes / 3)).strftime('%Y-%m-%dT%H:%M:%SZ')}</time>" if timed else ""
        ext = f"<extensions><gpxtpx:TrackPointExtension><gpxtpx:hr>{150 + i}</gpxtpx:hr></gpxtpx:TrackPointExtension></extensions>" if hr else ""
        pts += f'<trkpt lat="{48.85 + i * 0.01}" lon="2.35"><ele>{35 + i * 5}</ele>{t}{ext}</trkpt>'
    return (f'<?xml version="1.0"?><gpx version="1.1" creator="test" xmlns="http://www.topografix.com/GPX/1/1" '
            f'xmlns:gpxtpx="http://www.garmin.com/xmlschemas/TrackPointExtension/v1"><trk><name>Sortie test</name><type>cycling</type>'
            f"<trkseg>{pts}</trkseg></trk></gpx>").encode()


# ---------- lecture ----------

def test_fit_parses_totals():
    r = parse_activity(make_fit())
    assert (r["source"], r["sport"], r["duration_s"], r["distance_m"]) == ("fit", "run", 2700, 8000.0)
    assert (r["avg_hr"], r["max_hr"], r["calories"], r["elevation_m"]) == (152, 171, 480, 85.0)
    assert r["started_at"] == START.replace(tzinfo=None) and r["day"] == START.date() and r["garmin_id"].startswith("fit:")


def test_fit_strength_and_no_hr_stays_none():
    r = parse_activity(make_fit(hr=False, sport=10, sub_sport=20, km=0))
    assert r["sport"] == "strength" and r["avg_hr"] is None and r["max_hr"] is None and r["distance_m"] is None


def test_local_time_conversion():
    from zoneinfo import ZoneInfo
    late = datetime(2026, 3, 10, 23, 30, tzinfo=UTC)
    r = parse_activity(make_fit(start=late), ZoneInfo("Europe/Paris"))
    assert r["day"] == date(2026, 3, 11) and r["started_at"].hour == 0


def test_tcx_parses_totals_and_ascent():
    r = parse_activity(make_tcx())
    assert (r["source"], r["sport"], r["duration_s"], r["distance_m"], r["calories"]) == ("tcx", "run", 2700, 8000.0, 480)
    assert (r["avg_hr"], r["max_hr"]) == (150, 172) and r["elevation_m"] == 25.0


def test_tcx_without_hr_and_bike():
    r = parse_activity(make_tcx(hr=False, sport="Biking"))
    assert r["sport"] == "bike" and r["avg_hr"] is None and r["max_hr"] is None


def test_gpx_parses_distance_hr_and_duration():
    r = parse_activity(make_gpx())
    assert (r["source"], r["sport"], r["duration_s"]) == ("gpx", "bike", 1800)
    assert 3300 < r["distance_m"] < 3500 and r["avg_hr"] == 152 and r["max_hr"] == 153 and r["calories"] is None and r["name"] == "Sortie test"


def test_gpx_without_hr_or_time():
    assert parse_activity(make_gpx(hr=False))["avg_hr"] is None
    with pytest.raises(ImportRejected, match="horodatage"):
        parse_activity(make_gpx(timed=False))


def test_gpx_route_only_is_rejected():
    with pytest.raises(ImportRejected, match="trace"):
        parse_activity(b'<gpx xmlns="http://www.topografix.com/GPX/1/1"><rte><rtept lat="1" lon="2"/></rte></gpx>')


def test_format_is_sniffed_from_content_not_name():
    assert parse_activity(make_tcx())["source"] == "tcx"  # le nom du fichier n'intervient pas dans parse_activity
    assert parse_activity(b"\xef\xbb\xbf" + make_gpx())["source"] == "gpx"  # BOM UTF-8


@pytest.mark.parametrize("raw", [
    b"", b"hello world, ceci n'est pas une activite", b"\x00" * 64, bytes(range(256)) * 4,
    make_fit()[:60],  # tronqué
    make_fit()[:-2] + b"\x00\x00",  # CRC faux
    make_fit()[:20] + bytes([make_fit()[20] ^ 0xFF]) + make_fit()[21:],  # octet altéré
    b"<gpx><trk>", b"<html><body>page web</body></html>",
    b'<?xml version="1.0"?><TrainingCenterDatabase xmlns="http://www.garmin.com/xmlschemas/TrainingCenterDatabase/v2"></TrainingCenterDatabase>',
])
def test_corrupt_or_foreign_files_are_rejected_cleanly(raw):
    with pytest.raises(ImportRejected):
        parse_activity(raw)


def test_xml_entities_and_bombs_are_refused():
    bomb = (b'<?xml version="1.0"?><!DOCTYPE lolz [<!ENTITY a "aaaaaaaaaa"><!ENTITY b "&a;&a;&a;&a;&a;&a;&a;&a;&a;&a;">'
            b'<!ENTITY c "&b;&b;&b;&b;&b;&b;&b;&b;&b;&b;">]><gpx><trk><name>&c;</name></trk></gpx>')
    xxe = b'<?xml version="1.0"?><!DOCTYPE x [<!ENTITY e SYSTEM "file:///etc/passwd">]><gpx><trk><name>&e;</name></trk></gpx>'
    for raw in (bomb, xxe):
        with pytest.raises(ImportRejected, match="XML"):
            parse_activity(raw)


def test_sport_mapping():
    assert [map_sport(x) for x in ("Running", "trail_running", "Biking", "indoor_cycling", "Swimming", "hiking", "strength_training", "yoga", None)] == [
        "run", "run", "bike", "bike", "swim", "walk", "strength", "other", "other"]


def test_duplicate_rule():
    row = parse_activity(make_fit())
    near = {"garmin_id": "99", "started_at": row["started_at"] + timedelta(seconds=90), "duration_s": 2700 + 120}
    far = {"garmin_id": "98", "started_at": row["started_at"] + timedelta(minutes=10), "duration_s": 2700}
    other_len = {"garmin_id": "97", "started_at": row["started_at"], "duration_s": 600}
    assert is_duplicate(row, [near]) and not is_duplicate(row, [far, other_len])


# ---------- API ----------

@pytest.fixture
def ctx():
    repo = MemoryRepo()
    app.dependency_overrides[get_repo] = lambda: repo
    c = TestClient(app)
    uid = c.post("/auth/register", json={"name": "R", "email": "imp@example.org", "password": PW}).json()["id"]
    yield c, uid, repo
    app.dependency_overrides.clear()


def files(*items):
    return [{"name": n, "data": base64.b64encode(raw).decode()} for n, raw in items]


def post(c, uid, *items, tz=None):
    return c.post(f"/users/{uid}/activities/import", json={"files": files(*items), "tz": tz})


def test_requires_login():
    c = TestClient(app)
    assert c.post("/users/1/activities/import", json={"files": files(("a.fit", make_fit()))}).status_code in (401, 403)


def test_import_three_formats_then_reimport_is_idempotent(ctx):
    c, uid, repo = ctx
    d1, d2, d3 = (START - timedelta(days=n) for n in (2, 4, 6))
    batch = (("a.fit", make_fit(d1)), ("b.tcx", make_tcx(d2)), ("c.gpx", make_gpx(d3)))
    r = post(c, uid, *batch).json()
    assert r["imported"] == 3 and [x["status"] for x in r["results"]] == ["imported"] * 3
    again = post(c, uid, *batch).json()
    assert again["imported"] == 0 and again["duplicates"] == 3
    rows = repo.list_activities(uid, TODAY - timedelta(days=30), 100)
    assert len(rows) == 3 and {a["source"] for a in rows} == {"fit", "tcx", "gpx"}


def test_same_workout_in_two_formats_or_with_garmin_is_a_duplicate(ctx):
    c, uid, repo = ctx
    repo.upsert_activities(uid, [{"garmin_id": "123", "day": START.date(), "started_at": START.replace(tzinfo=None) + timedelta(seconds=40), "sport": "run",
                                  "type_key": "running", "name": "Montre", "duration_s": 2710, "distance_m": 8000.0, "elevation_m": None, "avg_hr": None,
                                  "max_hr": None, "calories": None, "training_load": None}])
    r = post(c, uid, ("x.fit", make_fit()), ("x.tcx", make_tcx())).json()
    assert r["duplicates"] == 2 and r["imported"] == 0
    assert len(repo.list_activities(uid, TODAY - timedelta(days=30), 100)) == 1
    r = post(c, uid, ("y.fit", make_fit(START - timedelta(days=3))), ("y.tcx", make_tcx(START - timedelta(days=3), minutes=44))).json()
    assert [x["status"] for x in r["results"]] == ["imported", "duplicate"]  # même séance en deux formats dans un seul envoi


def test_bad_file_does_not_block_the_others_and_never_500(ctx):
    c, uid, repo = ctx
    r = post(c, uid, ("ok.fit", make_fit()), ("cassé.fit", make_fit()[:50]), ("../../etc/passwd", b"nope"), ("photo.jpg", b"\xff\xd8\xff\xe0" + b"0" * 50))
    assert r.status_code == 200
    j = r.json()
    assert [x["status"] for x in j["results"]] == ["imported", "rejected", "rejected", "rejected"] and all(x["message"] for x in j["results"][1:])
    assert j["results"][2]["name"] == "passwd"  # jamais un chemin
    bad = c.post(f"/users/{uid}/activities/import", json={"files": [{"name": "x", "data": "!!pas du base64!!"}]})
    assert bad.status_code == 200 and bad.json()["results"][0]["status"] == "rejected"


def test_limits(ctx):
    c, uid, repo = ctx
    assert post(c, uid, *[(f"{i}.fit", make_fit(START - timedelta(days=i))) for i in range(21)]).status_code == 422
    assert c.post(f"/users/{uid}/activities/import", json={"files": []}).status_code == 422
    big = make_gpx() + b" " * (10 * 1024 * 1024)
    r = post(c, uid, ("big.gpx", big)).json()
    assert r["results"][0]["status"] == "rejected" and "volumineux" in r["results"][0]["message"]
    old = post(c, uid, ("old.fit", make_fit(START - timedelta(days=800)))).json()["results"][0]
    assert old["status"] == "rejected" and "2 ans" in old["message"]
    future = post(c, uid, ("f.fit", make_fit(START + timedelta(days=30)))).json()["results"][0]
    assert future["status"] == "rejected"
    assert repo.list_activities(uid, TODAY - timedelta(days=900), 100) == []


def test_isolation_between_users(ctx):
    c, uid, repo = ctx
    post(c, uid, ("a.fit", make_fit()))
    c.post("/auth/logout")
    other = c.post("/auth/register", json={"name": "E", "email": "imp2@example.org", "password": PW}).json()["id"]
    assert post(c, uid, ("a.fit", make_fit())).status_code == 403  # pas dans le compte d'un autre
    assert c.get(f"/users/{other}/garmin").json()["recent"] == []
    r = post(c, other, ("a.fit", make_fit())).json()  # le même fichier chez un autre utilisateur n'est pas un doublon
    assert r["imported"] == 1 and len(repo.list_activities(uid, TODAY - timedelta(days=30), 10)) == 1


def test_import_completes_planned_session_and_feeds_volume(ctx):
    c, uid, repo = ctx
    repo.add_sessions(uid, [{"day": START.date(), "kind": "run_easy", "title": "Footing", "duration_min": 45, "details": {}, "rules": ["C1"], "notes": []}])
    r = post(c, uid, ("a.fit", make_fit())).json()
    assert r["sessions_completed"] == 1
    s = repo.list_sessions(uid, TODAY - timedelta(days=5), None)[0]
    assert s["status"] == "done" and s["logged"]["source"] == "fit" and s["logged"]["minutes"] == 45 and s["logged"]["distance_km"] == 8.0
    again = post(c, uid, ("a.fit", make_fit())).json()
    assert again["sessions_completed"] == 0


def test_disconnecting_garmin_keeps_imported_files(ctx):
    c, uid, repo = ctx
    post(c, uid, ("a.fit", make_fit()))
    repo.delete_garmin(uid, True)
    assert len(repo.list_activities(uid, TODAY - timedelta(days=30), 10)) == 1
