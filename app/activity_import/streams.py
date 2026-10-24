"""Courbes simplifiées d'une activité à partir d'un fichier FIT, TCX ou GPX : fonctions pures (octets -> séries), sans réseau ni disque (règle ST25).

Seules les séries utiles aux graphiques sont gardées (temps, distance, FC, vitesse, altitude, cadence, puissance), moyennées en 300 à 500 points. Les positions GPS sont lues
uniquement pour calculer une distance de GPX sans capteur de distance, puis oubliées : aucune latitude ni longitude n'est renvoyée, stockée ou affichée.
Une valeur absente reste `None` (jamais 0) et les trous d'enregistrement (pauses) ne sont pas interpolés.
"""
import io
from datetime import datetime
from typing import Any

import fitdecode

from app.activity_import.parse import (
    ImportRejected,
    _fl,
    _fmt_time,
    _haversine,
    _hr,
    _kids,
    _local,
    _num,
    _text,
    map_sport,
    sniff,
)

MAX_POINTS = 400
MIN_POINTS = 10
MIN_DURATION_S = 30
MAX_SPLITS = 100
BOUNDS = {"speed": (0.0, 30.0), "alt": (-500.0, 9000.0), "cad": (0, 250), "power": (0, 2500)}  # au-delà : capteur défaillant, valeur ignorée
SERIES = ("dist", "hr", "speed", "alt", "cad", "power")


def _n(v: Any) -> float | None:
    return _fl(v) if isinstance(v, str) else _num(v)


def _bounded(kind: str, v: Any) -> float | None:
    n = _n(v)
    lo, hi = BOUNDS[kind]
    return n if n is not None and lo <= n <= hi else None


def _sample(ts: datetime, dist: Any = None, hr: Any = None, speed: Any = None, alt: Any = None, cad: Any = None, power: Any = None) -> dict[str, Any]:
    d = _n(dist)
    return {"ts": ts, "dist": d if d is not None and d >= 0 else None, "hr": _hr(hr), "speed": _bounded("speed", speed), "alt": _bounded("alt", alt),
            "cad": _bounded("cad", cad), "power": _bounded("power", power)}


def _mean(vals: list[float]) -> float | None:
    return sum(vals) / len(vals) if vals else None


def downsample(samples: list[dict[str, Any]], limit: int = MAX_POINTS) -> list[dict[str, Any]]:
    """Moyenne par intervalle de temps égal ; un intervalle sans mesure (pause) n'a pas de point. La distance garde sa dernière valeur."""
    if len(samples) <= limit:
        return samples
    width = samples[-1]["t"] / limit or 1.0
    bins: dict[int, list[dict[str, Any]]] = {}
    for s in samples:
        bins.setdefault(min(int(s["t"] / width), limit - 1), []).append(s)
    out = []
    for _, rows in sorted(bins.items()):
        point: dict[str, Any] = {"t": _mean([r["t"] for r in rows])}
        for k in SERIES:
            vals = [r[k] for r in rows if r[k] is not None]
            point[k] = (vals[-1] if k == "dist" else _mean(vals)) if vals else None
        out.append(point)
    return out


def km_splits(samples: list[dict[str, Any]]) -> list[dict[str, Any]]:
    """Un tour par kilomètre complet (temps interpolé au passage de chaque kilomètre) et le reste final s'il fait au moins 100 m."""
    pts = [s for s in samples if s["dist"] is not None]
    if len(pts) < 2 or pts[-1]["dist"] < 1000:
        return []
    out: list[dict[str, Any]] = []
    mark_t, mark_d, nxt = 0.0, 0.0, 1000.0
    hrs: list[int] = []
    prev = pts[0]
    for p in pts[1:]:
        if p["hr"]:
            hrs.append(p["hr"])
        while p["dist"] >= nxt and len(out) < MAX_SPLITS:
            span = p["dist"] - prev["dist"]
            t_cross = p["t"] if span <= 0 else prev["t"] + (p["t"] - prev["t"]) * (nxt - prev["dist"]) / span
            out.append({"i": len(out) + 1, "t0": round(mark_t), "dur_s": round(t_cross - mark_t), "dist_m": round(nxt - mark_d), "hr": round(sum(hrs) / len(hrs)) if hrs else None})
            mark_t, mark_d, nxt, hrs = t_cross, nxt, nxt + 1000.0, []
        prev = p
    rest = pts[-1]["dist"] - mark_d
    if rest >= 100 and len(out) < MAX_SPLITS:
        out.append({"i": len(out) + 1, "t0": round(mark_t), "dur_s": round(pts[-1]["t"] - mark_t), "dist_m": round(rest), "hr": round(sum(hrs) / len(hrs)) if hrs else None})
    return out


def lap_splits(laps: list[dict[str, Any]], t0: datetime) -> list[dict[str, Any]]:
    """Tours enregistrés par la montre (au moins deux) ; un tour sans début ni durée est ignoré."""
    if not 2 <= len(laps) <= MAX_SPLITS:
        return []
    return [{"i": i, "t0": round((lap["start"] - t0).total_seconds()), "dur_s": round(lap["dur_s"]), "dist_m": round(lap["dist_m"]) if lap.get("dist_m") else None, "hr": _hr(lap.get("hr"))}
            for i, lap in enumerate(laps, 1) if lap.get("start") and lap.get("dur_s")]


def _round(vals: list[Any], digits: int | None) -> list[Any] | None:
    if not any(v is not None for v in vals):
        return None
    return [None if v is None else (round(v) if digits is None else round(v, digits)) for v in vals]


def build(samples: list[dict[str, Any]], laps: list[dict[str, Any]], cad_factor: int = 1) -> dict[str, Any] | None:
    """Échantillons horodatés (`ts` en datetime) et tours -> séries prêtes à stocker, ou None quand il y a trop peu à tracer."""
    rows = sorted((s for s in samples if isinstance(s.get("ts"), datetime)), key=lambda s: s["ts"])
    if not rows:
        return None
    t0 = rows[0]["ts"]
    clean: list[dict[str, Any]] = []
    for s in rows:
        t = (s["ts"] - t0).total_seconds()
        if clean and t <= clean[-1]["t"]:
            continue
        clean.append({**s, "t": t})
    if len(clean) < MIN_POINTS or clean[-1]["t"] < MIN_DURATION_S or not any(s[k] is not None for s in clean for k in ("hr", "speed", "alt", "cad", "power", "dist")):
        return None
    if cad_factor != 1:  # FIT de course : la cadence compte les foulées d'un seul pied, l'allure se lit en pas par minute
        for s in clean:
            s["cad"] = s["cad"] * cad_factor if s["cad"] is not None else None
    splits = {"km": km_splits(clean), "laps": lap_splits(laps, t0)}
    pts = downsample(clean)
    t = [round(p["t"]) for p in pts]
    dist = _round([p["dist"] for p in pts], 1)
    speed = _round([p["speed"] for p in pts], 2)
    if speed is None and dist is not None:  # pas de capteur de vitesse : dérivée de la distance entre deux points
        speed = [None] + [round(max(0.0, (b - a) / (t[i + 1] - t[i])), 2) if a is not None and b is not None and t[i + 1] > t[i] else None
                          for i, (a, b) in enumerate(zip(dist, dist[1:], strict=False))]
        speed = speed if any(v is not None for v in speed) else None
    return {"n": len(pts), "duration_s": t[-1], "t": t, "dist": dist, "hr": _round([p["hr"] for p in pts], None), "speed": speed, "alt": _round([p["alt"] for p in pts], 1),
            "cad": _round([p["cad"] for p in pts], None), "power": _round([p["power"] for p in pts], None), "splits": splits}


# ---------- FIT ----------

def fit_streams(raw: bytes) -> dict[str, Any] | None:
    records: list[dict[str, Any]] = []
    laps: list[dict[str, Any]] = []
    sport = "other"
    with fitdecode.FitReader(io.BytesIO(raw), check_crc=fitdecode.CrcCheck.RAISE) as fit:
        for f in fit:
            if not isinstance(f, fitdecode.FitDataMessage):
                continue

            def v(k: str, f: Any = f) -> Any:
                return f.get_value(k, fallback=None) if f.has_field(k) else None

            if f.name == "record" and isinstance(v("timestamp"), datetime):
                alt = v("enhanced_altitude") if v("enhanced_altitude") is not None else v("altitude")
                speed = v("enhanced_speed") if v("enhanced_speed") is not None else v("speed")
                records.append(_sample(v("timestamp"), v("distance"), v("heart_rate"), speed, alt, v("cadence"), v("power")))
            elif f.name == "lap" and isinstance(v("start_time"), datetime):
                laps.append({"start": v("start_time"), "dur_s": _num(v("total_elapsed_time")), "dist_m": _num(v("total_distance")), "hr": v("avg_heart_rate")})
            elif f.name == "session":
                sport = map_sport(v("sub_sport"), v("sport"))
    return build(records, laps, 2 if sport == "run" else 1)


# ---------- TCX et GPX ----------

def _ext(p: Any, name: str) -> float | None:
    return next((_fl(n.text) for n in p.iter() if _local(n.tag) == name and n.text), None)


def tcx_streams(root: Any) -> dict[str, Any] | None:
    act = next((a for acts in _kids(root, "Activities") for a in _kids(acts, "Activity")), None)
    if act is None:
        return None
    records: list[dict[str, Any]] = []
    laps: list[dict[str, Any]] = []
    for lap in _kids(act, "Lap"):
        start = _fmt_time(lap.get("StartTime"))
        dur = _fl(_text(lap, "TotalTimeSeconds"))
        laps.append({"start": start, "dur_s": dur, "dist_m": _fl(_text(lap, "DistanceMeters")), "hr": _text(lap, "AverageHeartRateBpm", "Value")})
        for tr in _kids(lap, "Track"):
            for p in _kids(tr, "Trackpoint"):
                ts = _fmt_time(_text(p, "Time"))
                if ts is None:
                    continue
                run_cad = _ext(p, "RunCadence")  # foulées d'un seul pied (Garmin) : doublées pour obtenir des pas par minute
                cad = run_cad * 2 if run_cad is not None else _fl(_text(p, "Cadence"))
                records.append(_sample(ts, _text(p, "DistanceMeters"), _text(p, "HeartRateBpm", "Value"), _ext(p, "Speed"), _text(p, "AltitudeMeters"), cad, _ext(p, "Watts")))
    return build(records, laps)


def gpx_streams(root: Any) -> dict[str, Any] | None:
    records: list[dict[str, Any]] = []
    total, last = 0.0, None
    for trk in _kids(root, "trk"):
        for seg in _kids(trk, "trkseg"):
            for p in _kids(seg, "trkpt"):
                lat, lon, ts = _fl(p.get("lat")), _fl(p.get("lon")), _fmt_time(_text(p, "time"))
                if lat is None or lon is None or ts is None or not (-90 <= lat <= 90 and -180 <= lon <= 180):
                    continue
                if last is not None:
                    total += _haversine(last, (lat, lon))
                last = (lat, lon)  # position utilisée pour la distance seulement, jamais copiée dans les séries
                hr = next((_hr(n.text) for n in p.iter() if _local(n.tag) in ("hr", "heartrate") and _hr(n.text)), None)
                records.append(_sample(ts, total, hr, None, _text(p, "ele")))
    return build(records, [])


def parse_streams(raw: bytes) -> dict[str, Any] | None:
    """Octets d'un fichier d'activité -> séries simplifiées, ou None (fichier sans courbe exploitable, illisible ou non reconnu). Ne lève jamais."""
    from defusedxml import ElementTree as SafeET

    try:
        if sniff(raw) == "fit":
            return fit_streams(raw)
        root = SafeET.fromstring(raw, forbid_dtd=True)
        kind = _local(root.tag)
        return tcx_streams(root) if kind == "TrainingCenterDatabase" else gpx_streams(root) if kind == "gpx" else None
    except ImportRejected:
        return None
    except Exception:  # noqa: BLE001 - les courbes sont un plus : un fichier hostile ou étrange ne doit jamais faire échouer l'import
        return None
