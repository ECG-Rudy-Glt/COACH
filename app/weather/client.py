"""Prévision Open-Meteo (gratuite, sans clé) : géocodage d'une ville et prévision horaire d'une position arrondie.

Confidentialité : seules les coordonnées ARRONDIES à 0,1° (environ 11 km) quittent le serveur, jamais l'identité, le compte ni une position GPS précise.
Le géocodage envoie le nom de ville saisi. Désactivable pour l'auto-hébergement : WEATHER_ENABLED=0. Échec silencieux : le plan reste utilisable.
Adresses remplaçables (miroir, instance auto-hébergée d'Open-Meteo) : WEATHER_BASE_URL, WEATHER_GEOCODE_URL."""
import json
import threading
import time
import urllib.error
import urllib.parse
import urllib.request
from typing import Any

from app.config import VERSION, env

TIMEOUT_S = 4
MAX_BYTES = 1_000_000
CACHE_TTL_S = 2 * 3600  # entre 1 et 3 h : la prévision à 7 jours bouge peu, et on ménage le service gratuit
FAIL_TTL_S = 600  # un échec n'est pas retenté pendant 10 minutes (pas de rafale d'appels si le service est tombé)
CACHE_MAX = 500
USER_AGENT = f"COACH-selfhosted/{VERSION} (+https://github.com/ECG-Rudy-Glt/COACH)"
HOURLY = "temperature_2m,apparent_temperature,precipitation_probability,precipitation,wind_gusts_10m,weather_code"

_cache: dict[tuple[float, float], tuple[float, dict[str, Any] | None]] = {}
_lock = threading.Lock()


def server_enabled() -> bool:
    return env("WEATHER_ENABLED", "1").lower() not in ("0", "false", "no", "off", "non")


def _base(name: str, default: str) -> str | None:
    url = env(name, default).rstrip("/")
    return url if url.startswith(("https://", "http://")) else None


def round_position(lat: float, lon: float) -> tuple[float, float]:
    """Arrondi à 0,1° AVANT tout appel externe ; `+ 0.0` évite « -0.0 »."""
    return round(float(lat), 1) + 0.0, round(float(lon), 1) + 0.0


def _get_json(url: str) -> dict[str, Any] | None:
    req = urllib.request.Request(url, headers={"User-Agent": USER_AGENT, "Accept": "application/json"})  # noqa: S310 : schéma http(s) vérifié par _base()
    try:
        with urllib.request.urlopen(req, timeout=TIMEOUT_S) as r:  # noqa: S310
            data = json.loads(r.read(MAX_BYTES + 1)[:MAX_BYTES])
    except (urllib.error.URLError, TimeoutError, ValueError, OSError):
        return None
    return data if isinstance(data, dict) else None


def geocode(query: str) -> list[dict[str, Any]]:
    """Villes correspondant au texte saisi, coordonnées déjà arrondies. Liste vide si désactivé, texte vide ou service injoignable."""
    q = " ".join(query.split())[:80]
    base = _base("WEATHER_GEOCODE_URL", "https://geocoding-api.open-meteo.com")
    if not server_enabled() or len(q) < 2 or not base:
        return []
    data = _get_json(f"{base}/v1/search?{urllib.parse.urlencode({'name': q, 'count': 5, 'language': 'fr', 'format': 'json'})}")
    out = []
    for r in (data or {}).get("results") or []:
        try:
            lat, lon = round_position(r["latitude"], r["longitude"])
        except (KeyError, TypeError, ValueError):
            continue
        if abs(lat) > 90 or abs(lon) > 180 or not r.get("name"):
            continue
        out.append({"name": str(r["name"])[:60], "admin": str(r.get("admin1") or "")[:60], "country": str(r.get("country") or "")[:60], "lat": lat, "lon": lon})
    return out


def parse_forecast(payload: dict[str, Any]) -> dict[str, dict[int, dict[str, float | None]]] | None:
    """{jour ISO: {heure: {t, feels, pp, mm, gust, code}}} (heure locale du lieu) ; None si la réponse est inutilisable. Fonction pure."""
    h = payload.get("hourly")
    if not isinstance(h, dict) or not isinstance(h.get("time"), list):
        return None

    def col(name: str) -> list[Any]:
        v = h.get(name)
        return v if isinstance(v, list) else []

    cols = {"t": col("temperature_2m"), "feels": col("apparent_temperature"), "pp": col("precipitation_probability"), "mm": col("precipitation"),
            "gust": col("wind_gusts_10m"), "code": col("weather_code")}
    out: dict[str, dict[int, dict[str, float | None]]] = {}
    for i, stamp in enumerate(h["time"]):
        try:
            day, hh = str(stamp).split("T")
            hour = int(hh[:2])
        except ValueError:
            continue
        row: dict[str, float | None] = {}
        for k, values in cols.items():
            v = values[i] if i < len(values) else None
            row[k] = float(v) if isinstance(v, int | float) and not isinstance(v, bool) else None
        out.setdefault(day, {})[hour] = row
    return out or None


def forecast(lat: float, lon: float, now: float | None = None) -> dict[str, dict[int, dict[str, float | None]]] | None:
    """Prévision à 7 jours d'une position arrondie, en cache 2 h par position arrondie. None si désactivé ou injoignable (jamais d'exception)."""
    base = _base("WEATHER_BASE_URL", "https://api.open-meteo.com")
    if not server_enabled() or not base:
        return None
    key = round_position(lat, lon)  # même si l'appelant a oublié d'arrondir
    t = time.time() if now is None else now
    with _lock:
        hit = _cache.get(key)
        if hit and t - hit[0] < (CACHE_TTL_S if hit[1] else FAIL_TTL_S):
            return hit[1]
    query = urllib.parse.urlencode({"latitude": key[0], "longitude": key[1], "hourly": HOURLY, "timezone": "auto", "forecast_days": 7})
    data = _get_json(f"{base}/v1/forecast?{query}")
    parsed = parse_forecast(data) if data else None
    with _lock:
        if len(_cache) >= CACHE_MAX:
            _cache.clear()
        _cache[key] = (t, parsed)
    return parsed


def clear_cache() -> None:
    with _lock:
        _cache.clear()
