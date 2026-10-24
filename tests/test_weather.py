"""Météo des séances en extérieur (W1 à W8) : règles, cache, arrondi de la position, désactivation, API et contexte du coach. Aucun appel réseau réel."""
from datetime import date, timedelta
from urllib.parse import parse_qs, urlparse

import pytest
from fastapi.testclient import TestClient

from app.auth import reset_rate_limits
from app.coach import service as coach_service
from app.main import app, get_repo
from app.repo import MemoryRepo
from app.weather import client, rules

PW = "un-mot-de-passe-solide"
TODAY = date.today()


def hourly(over: dict[str, dict[int, dict]] | None = None, calm: bool = True) -> dict:
    """Prévision de 7 jours, par défaut paisible ; `over` = {jour ISO: {heure: valeurs}} remplace des heures."""
    times, cols = [], {k: [] for k in ("temperature_2m", "apparent_temperature", "precipitation_probability", "precipitation", "wind_gusts_10m", "weather_code")}
    for d in range(7):
        iso = (TODAY + timedelta(days=d)).isoformat()
        for h in range(24):
            row = {"temperature_2m": 14, "apparent_temperature": 14, "precipitation_probability": 5, "precipitation": 0.0, "wind_gusts_10m": 15, "weather_code": 1}
            row.update(((over or {}).get(iso) or {}).get(h, {}))
            times.append(f"{iso}T{h:02d}:00")
            for k in cols:
                cols[k].append(row[k])
    return {"hourly": {"time": times, **cols}}


@pytest.fixture(autouse=True)
def net(monkeypatch):
    """Faux Open-Meteo : enregistre les adresses appelées ; `net.payload` = ce que renvoie la prévision, `net.fail` = service injoignable."""
    client.clear_cache()
    monkeypatch.delenv("WEATHER_ENABLED", raising=False)

    class Net:
        urls: list[str] = []
        payload: dict | None = hourly()
        fail = False
        geo = {"results": [{"name": "Lyon", "admin1": "Auvergne-Rhône-Alpes", "country": "France", "latitude": 45.74846, "longitude": 4.84671}]}

    n = Net()
    n.urls = []

    def fake(url):
        n.urls.append(url)
        if n.fail:
            return None
        return n.geo if "geocoding" in url else n.payload

    monkeypatch.setattr(client, "_get_json", fake)
    return n


@pytest.fixture
def env():
    reset_rate_limits()
    repo = MemoryRepo()
    app.dependency_overrides[get_repo] = lambda: repo
    c = TestClient(app)
    uid = c.post("/auth/register", json={"name": "R", "email": "m@example.org", "password": PW}).json()["id"]
    yield c, repo, uid
    app.dependency_overrides.clear()


def session(repo, uid, day, kind="run_easy", minutes=60, title="Footing"):
    return repo.add_session(uid, {"day": day, "kind": kind, "title": title, "duration_min": minutes, "details": {}, "rules": [], "notes": [], "status": "planned", "logged": None})


def enable(c, uid, hour=18):
    assert c.put(f"/users/{uid}/weather/place", json={"name": "Lyon", "lat": 45.74846, "lon": 4.84671}).status_code == 200
    c.put(f"/users/{uid}/weather/settings", json={"hour": hour})


def hours(**kw):
    base = {"t": 14, "feels": 14, "pp": 5, "mm": 0.0, "gust": 15, "code": 1}
    return {h: {**base, **kw} for h in range(24)}


# ---------- règles ----------

@pytest.mark.parametrize("kw,status,rule", [
    ({}, "ok", None),
    ({"code": 95}, "avoid", "W1"),
    ({"gust": 41}, "watch", "W2"), ({"gust": 52}, "avoid", "W2"),
    ({"pp": 70, "mm": 2.5}, "watch", "W3"), ({"pp": 90, "mm": 4.0}, "avoid", "W3"), ({"pp": 90, "mm": 1.0}, "ok", None),
    ({"feels": 32}, "watch", "W4"), ({"feels": 39}, "avoid", "W4"), ({"feels": 31}, "ok", None),
    ({"feels": -10}, "watch", "W5"), ({"feels": -28}, "avoid", "W5"), ({"feels": -9}, "ok", None),
    ({"t": 1, "mm": 0.3}, "avoid", "W6"), ({"t": 3, "mm": 0.3}, "ok", None),
])
def test_thresholds(kw, status, rule):
    a = rules.assess(hours(**kw), 18, 60)
    assert a["status"] == status
    assert (rule is None and not a["reasons"]) or rule in {r["rule"] for r in a["reasons"]}
    assert all(r["adapt"] and r["text"] for r in a["reasons"])


def test_storm_nearby_is_watch_and_window_follows_duration():
    h = hours()
    h[20]["code"] = 96
    assert rules.assess(h, 18, 60)["status"] == "watch"  # 2 h plus tard : à surveiller
    assert rules.assess(h, 18, 150)["status"] == "avoid"  # la séance dure jusqu'à 20 h
    assert rules.window(18, 150) == [18, 19, 20] and rules.window(23, 120) == [23]


def test_ice_after_rain_and_missing_data():
    h = hours(t=0)
    h[15]["mm"] = 1.0
    assert rules.assess(h, 18, 60)["reasons"][0]["rule"] == "W6" and rules.assess(h, 18, 60)["status"] == "watch"
    assert rules.assess({}, 18, 60) is None


def test_parse_forecast_is_tolerant():
    assert client.parse_forecast({}) is None and client.parse_forecast({"hourly": {"time": "x"}}) is None
    p = client.parse_forecast({"hourly": {"time": ["2026-01-01T07:00", "bad"], "temperature_2m": [3.5]}})
    assert p == {"2026-01-01": {7: {"t": 3.5, "feels": None, "pp": None, "mm": None, "gust": None, "code": None}}}


# ---------- client : arrondi, cache, désactivation ----------

def test_position_is_rounded_before_any_call(net):
    assert client.round_position(45.74846, 4.84671) == (45.7, 4.8) and client.round_position(-0.04, -0.04) == (0.0, 0.0)
    client.forecast(45.74846, 4.84671)
    q = parse_qs(urlparse(net.urls[0]).query)
    assert q["latitude"] == ["45.7"] and q["longitude"] == ["4.8"] and set(q) == {"latitude", "longitude", "hourly", "timezone", "forecast_days"}
    assert "45.74" not in net.urls[0]


def test_cache_per_rounded_position_and_expiry(net):
    client.forecast(45.71, 4.81, now=1000)
    client.forecast(45.74, 4.84, now=1500)  # même case de 0,1° : pas de nouvel appel
    assert len(net.urls) == 1
    client.forecast(45.71, 4.81, now=1000 + client.CACHE_TTL_S + 1)
    client.forecast(48.9, 2.3, now=1500)
    assert len(net.urls) == 3


def test_failure_is_silent_and_not_hammered(net):
    net.fail = True
    assert client.forecast(45.7, 4.8, now=0) is None and client.forecast(45.7, 4.8, now=60) is None
    assert len(net.urls) == 1
    net.fail = False
    assert client.forecast(45.7, 4.8, now=client.FAIL_TTL_S + 1) is not None


def test_server_switch_blocks_every_external_call(net, monkeypatch):
    monkeypatch.setenv("WEATHER_ENABLED", "0")
    assert client.forecast(45.7, 4.8) is None and client.geocode("Lyon") == [] and net.urls == []


def test_geocode_rounds_and_ignores_garbage(net):
    net.geo = {"results": [{"name": "Lyon", "latitude": 45.74846, "longitude": 4.84671}, {"name": "X", "latitude": 99, "longitude": 0}, {"latitude": 1, "longitude": 1}, "bad"]}
    out = client.geocode("  Lyon ")
    assert out == [{"name": "Lyon", "admin": "", "country": "", "lat": 45.7, "lon": 4.8}]
    assert client.geocode("a") == []


# ---------- API ----------

def test_disabled_by_default_and_no_call_without_city(env, net):
    c, repo, uid = env
    session(repo, uid, TODAY)
    s = c.get(f"/users/{uid}/weather/settings").json()
    assert s["enabled"] is False and s["place"] is None and s["server_enabled"] is True
    o = c.get(f"/users/{uid}/weather/outlook").json()
    assert o["enabled"] is False and o["items"] == [] and net.urls == []
    assert c.put(f"/users/{uid}/weather/settings", json={"enabled": True}).status_code == 422


def test_place_is_stored_rounded_and_can_be_toggled_and_removed(env, net):
    c, repo, uid = env
    s = c.put(f"/users/{uid}/weather/place", json={"name": " Lyon ", "lat": 45.74846, "lon": 4.84671}).json()
    assert s["place"] == {"name": "Lyon", "lat": 45.7, "lon": 4.8} and s["enabled"] is True
    assert "45.74" not in str(repo.list_facts(uid))
    assert c.put(f"/users/{uid}/weather/settings", json={"enabled": False}).json()["enabled"] is False
    session(repo, uid, TODAY)
    assert c.get(f"/users/{uid}/weather/outlook").json()["enabled"] is False and net.urls == []
    assert c.put(f"/users/{uid}/weather/settings", json={"enabled": True, "hour": 7}).json()["hour"] == 7
    assert c.delete(f"/users/{uid}/weather/place").json() == {"server_enabled": True, "place": None, "enabled": False, "hour": 7}
    assert c.put(f"/users/{uid}/weather/place", json={"lat": 120, "lon": 0}).status_code == 422
    assert c.put(f"/users/{uid}/weather/settings", json={"hour": 24}).status_code == 422


def test_server_switch_disables_the_feature(env, net, monkeypatch):
    c, repo, uid = env
    enable(c, uid)
    net.urls.clear()
    monkeypatch.setenv("WEATHER_ENABLED", "0")
    session(repo, uid, TODAY)
    assert c.get(f"/users/{uid}/weather/outlook").json()["enabled"] is False
    assert c.get(f"/users/{uid}/weather/geocode?q=Lyon").status_code == 503
    assert c.put(f"/users/{uid}/weather/place", json={"lat": 1, "lon": 1}).status_code == 503
    assert net.urls == []


def test_auth_and_isolation(env):
    c, repo, uid = env
    other = TestClient(app)
    assert other.get(f"/users/{uid}/weather/outlook").status_code == 401
    other.post("/auth/register", json={"name": "B", "email": "b@example.org", "password": PW})
    assert other.get(f"/users/{uid}/weather/settings").status_code == 403


def test_geocode_endpoint_and_rate_limit(env, net, monkeypatch):
    c, repo, uid = env
    assert c.get(f"/users/{uid}/weather/geocode?q=Lyon").json()["results"][0]["lat"] == 45.7
    assert c.get(f"/users/{uid}/weather/geocode?q=L").status_code == 422
    from app.weather import api
    monkeypatch.setattr(api, "GEOCODE_PER_HOUR", 2)
    c.get(f"/users/{uid}/weather/geocode?q=Lyon")
    assert c.get(f"/users/{uid}/weather/geocode?q=Lyon").status_code == 429


def test_outlook_flags_outdoor_session_and_the_suggested_move_uses_the_existing_endpoint(env, net):
    c, repo, uid = env
    day = TODAY + timedelta(days=1) if TODAY.weekday() < 6 else TODAY
    net.payload = hourly({day.isoformat(): {h: {"weather_code": 95} for h in range(24)}})
    enable(c, uid)
    s = session(repo, uid, day, "run_long", 90, "Sortie longue")
    session(repo, uid, day, "strength_upper", 45, "Haut du corps")  # non extérieure : jamais évaluée
    o = c.get(f"/users/{uid}/weather/outlook").json()
    assert o["enabled"] and [i["session_id"] for i in o["items"]] == [s["id"]]
    item = o["items"][0]
    assert item["status"] == "avoid" and item["reasons"][0]["rule"] == "W1" and item["forecast"]["storm"] is True
    assert "Prévision indicative" in o["disclaimer"]
    sug = item["suggestion"]
    if sug:
        monday = day - timedelta(days=day.weekday())
        assert monday <= date.fromisoformat(sug["day"]) < monday + timedelta(days=7) and sug["day"] != day.isoformat()
        r = c.patch(f"/users/{uid}/plan/sessions/{s['id']}/move", json={"day": sug["day"]})
        assert r.status_code == 200 and r.json()["warnings"] == []
    # la météo seule ne déplace jamais rien
    assert c.get(f"/users/{uid}/weather/outlook").status_code == 200


WEEK = date(2026, 11, 2)  # un lundi : semaine de test fixe, indépendante du jour d'exécution


def week_forecast(**bad):
    fc = {(WEEK + timedelta(days=i)).isoformat(): hours() for i in range(7)}
    for i, kw in bad.items():
        fc[(WEEK + timedelta(days=int(i[1:]))).isoformat()] = hours(**kw)
    return fc


def test_suggestion_skips_bad_weather_busy_days_and_spacing_conflicts(env, monkeypatch):
    from app.weather import service
    c, repo, uid = env
    monkeypatch.setattr(client, "forecast", lambda lat, lon, now=None: week_forecast(d2={"code": 95}, d6={"gust": 70}))
    enable(c, uid)
    long_ = session(repo, uid, WEEK + timedelta(days=2), "run_long", 90, "Sortie longue")
    session(repo, uid, WEEK, "strength_lower", 50, "Jambes")  # lundi : jambes, le mardi serait trop proche (I2)
    session(repo, uid, WEEK + timedelta(days=3), "strength_lower", 50, "Jambes")  # jeudi : occupé, et le vendredi serait trop proche
    o = service.outlook(repo, uid, WEEK)
    item = next(i for i in o["items"] if i["session_id"] == long_["id"])
    assert item["status"] == "avoid"
    assert item["suggestion"]["day"] == (WEEK + timedelta(days=5)).isoformat() and item["suggestion"]["weekday"] == "samedi"  # dimanche : rafales


def test_no_suggestion_when_the_whole_week_is_bad_but_adaptation_is_given(env, monkeypatch):
    from app.weather import service
    c, repo, uid = env
    monkeypatch.setattr(client, "forecast", lambda lat, lon, now=None: week_forecast(**{f"d{i}": {"feels": 40} for i in range(7)}))
    enable(c, uid)
    session(repo, uid, WEEK + timedelta(days=1), "run_easy", 45)
    item = service.outlook(repo, uid, WEEK)["items"][0]
    assert item["status"] == "avoid" and item["suggestion"] is None and "plus tôt" in item["reasons"][0]["adapt"]


def test_only_planned_outdoor_sessions_in_the_next_seven_days(env, monkeypatch):
    from app.weather import service
    c, repo, uid = env
    monkeypatch.setattr(client, "forecast", lambda lat, lon, now=None: week_forecast())
    enable(c, uid)
    done = session(repo, uid, WEEK + timedelta(days=1))
    repo.update_session(uid, done["id"], "done", None)
    session(repo, uid, WEEK + timedelta(days=9))  # au-delà de l'horizon
    session(repo, uid, WEEK + timedelta(days=2), "run_easy", 30, "Footing")
    assert [i["title"] for i in service.outlook(repo, uid, WEEK)["items"]] == ["Footing"]


def test_unavailable_forecast_is_silent(env, net):
    c, repo, uid = env
    enable(c, uid)
    session(repo, uid, TODAY)
    net.fail = True
    client.clear_cache()
    o = c.get(f"/users/{uid}/weather/outlook").json()
    assert o["enabled"] is True and o["unavailable"] is True and o["items"] == []


def test_ok_session_has_no_suggestion(env, net):
    c, repo, uid = env
    enable(c, uid)
    session(repo, uid, TODAY, "sport_bike", 90, "Vélo")
    i = c.get(f"/users/{uid}/weather/outlook").json()["items"][0]
    assert i["status"] == "ok" and i["reasons"] == [] and i["suggestion"] is None


# ---------- coach ----------

def test_coach_gets_weather_only_when_enabled(env, net):
    c, repo, uid = env
    session(repo, uid, TODAY + timedelta(days=1), "run_easy")
    assert "meteo_semaine" not in coach_service.build_context(repo, uid, TODAY)
    assert net.urls == []
    enable(c, uid)
    net.payload = hourly({(TODAY + timedelta(days=1)).isoformat(): {18: {"wind_gusts_10m": 70}}})
    ctx = coach_service.build_context(repo, uid, TODAY)
    assert ctx["meteo_semaine"][0]["statut"] == "avoid" and ctx["meteo_semaine"][0]["regles"] == ["W2"]
    c.put(f"/users/{uid}/weather/settings", json={"enabled": False})
    assert "meteo_semaine" not in coach_service.build_context(repo, uid, TODAY)


def test_server_texts_are_translated_to_english():
    from app import i18n
    d = i18n.dictionary("en")
    a = rules.assess(hours(gust=70, code=95, feels=40), 18, 60)
    for r in a["reasons"]:
        assert d.lookup(r["text"]) != r["text"], r["text"]
        assert d.lookup(r["adapt"]) != r["adapt"], r["adapt"]
    assert d.lookup("Rafales prévues jusqu'à 70 km/h (vent de force 7 ou plus).").startswith("Gusts forecast")
