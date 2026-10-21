"""Lecture des fichiers d'activité FIT, TCX et GPX : fonctions pures (octets -> ligne d'activité), sans réseau ni disque.

Le format est reconnu par le contenu, jamais par l'extension. Une activité inutilisable lève `ImportRejected` avec un message
destiné à l'utilisateur ; aucune autre exception ne sort de `parse_activity`. Une valeur absente reste `None` (jamais 0).
"""
import hashlib
import io
import math
from datetime import UTC, date, datetime
from struct import error as struct_error
from typing import Any
from xml.etree.ElementTree import Element, ParseError

import fitdecode
from defusedxml import DefusedXmlException
from defusedxml import ElementTree as SafeET

MAX_FILE_BYTES = 10 * 1024 * 1024
MAX_DURATION_S = 7 * 24 * 3600  # une « activité » de plus d'une semaine est un fichier mal formé
EARTH_RADIUS_M = 6_371_000
ASCENT_STEP_M = 3.0  # hystérésis : le bruit de l'altimètre ne doit pas gonfler le dénivelé


class ImportRejected(Exception):
    """Fichier refusé ; le message est affiché tel quel (en français, clé de traduction)."""


def sniff(raw: bytes) -> str:
    """'fit' | 'xml' d'après les premiers octets ; ImportRejected sinon."""
    if len(raw) >= 12 and raw[8:12] == b".FIT":
        return "fit"
    head = raw[:512].lstrip(b"\xef\xbb\xbf \t\r\n")
    if head.startswith(b"<"):
        return "xml"
    raise ImportRejected("Format non reconnu : le fichier n'est ni FIT, ni TCX, ni GPX.")


def map_sport(*labels: Any) -> str:
    """Libellé libre d'une marque -> sport interne (run|bike|strength|walk|swim|other). Les libellés sont testés dans l'ordre."""
    for label in labels:
        t = str(label or "").lower().replace(" ", "_")
        if not t:
            continue
        for words, sport in ((("strength", "weight", "hiit", "crossfit", "cross_training", "fitness_equipment", "functional"), "strength"),
                             (("run", "jog", "treadmill"), "run"), (("bik", "cycl", "ride", "ebike", "velo"), "bike"),
                             (("swim",), "swim"), (("walk", "hik"), "walk")):
            if any(w in t for w in words):
                return sport
    return "other"


def _haversine(a: tuple[float, float], b: tuple[float, float]) -> float:
    p1, p2 = math.radians(a[0]), math.radians(b[0])
    dp, dl = p2 - p1, math.radians(b[1] - a[1])
    h = math.sin(dp / 2) ** 2 + math.cos(p1) * math.cos(p2) * math.sin(dl / 2) ** 2
    return 2 * EARTH_RADIUS_M * math.asin(min(1.0, math.sqrt(h)))


def _ascent(alts: list[float]) -> float | None:
    if len(alts) < 2:
        return None
    total, ref = 0.0, alts[0]
    for a in alts[1:]:
        if a - ref >= ASCENT_STEP_M:
            total += a - ref
            ref = a
        elif ref - a >= ASCENT_STEP_M:
            ref = a
    return round(total, 1)


def _hr(v: Any) -> int | None:
    try:
        n = round(float(v))
    except (TypeError, ValueError):
        return None
    return n if 30 <= n <= 250 else None


def _num(v: Any) -> float | None:
    return float(v) if isinstance(v, int | float) and not isinstance(v, bool) and math.isfinite(v) else None


def _aware_utc(dt: datetime) -> datetime:
    return dt.replace(tzinfo=UTC) if dt.tzinfo is None else dt.astimezone(UTC)


def _fmt_time(s: str | None) -> datetime | None:
    if not s:
        return None
    try:
        return _aware_utc(datetime.fromisoformat(s.strip().replace("Z", "+00:00")))
    except ValueError:
        return None


def _row(source: str, sport: str, start: datetime, duration_s: float | None, distance_m: float | None, ascent: float | None,
         hrs: list[int], avg_hr: int | None, max_hr: int | None, calories: Any, name: str | None, type_key: str | None) -> dict[str, Any]:
    """Ligne neutre (début en UTC) ; `parse_activity` la convertit en heure locale pour `day`/`started_at`."""
    if duration_s is None or duration_s < 1:
        raise ImportRejected("Durée absente ou nulle : le fichier ne contient pas d'activité exploitable.")
    if duration_s > MAX_DURATION_S:
        raise ImportRejected("Durée incohérente (plus de 7 jours) : fichier ignoré.")
    avg_hr = _hr(avg_hr) or (_hr(sum(hrs) / len(hrs)) if hrs else None)
    max_hr = _hr(max_hr) or (max(hrs) if hrs else None)
    cal = _num(calories)
    return {"source": source, "sport": sport, "start_utc": _aware_utc(start), "duration_s": int(round(duration_s)),
            "distance_m": round(distance_m, 1) if distance_m and distance_m > 0 else None, "elevation_m": ascent,
            "avg_hr": avg_hr, "max_hr": max_hr, "calories": int(cal) if cal and cal > 0 else None,
            "name": (name or "").strip()[:120] or None, "type_key": type_key}


# ---------- FIT ----------

def parse_fit(raw: bytes) -> dict[str, Any]:
    sessions: list[Any] = []
    records: list[Any] = []
    try:
        with fitdecode.FitReader(io.BytesIO(raw), check_crc=fitdecode.CrcCheck.RAISE) as fit:
            for frame in fit:
                if not isinstance(frame, fitdecode.FitDataMessage):
                    continue
                if frame.name == "session":
                    sessions.append(frame)
                elif frame.name == "record":
                    records.append(frame)
    except (fitdecode.FitError, ValueError, OverflowError, struct_error, EOFError, KeyError, IndexError) as e:
        raise ImportRejected("Fichier FIT corrompu ou incomplet.") from e

    def val(f: Any, k: str) -> Any:
        return f.get_value(k, fallback=None) if f.has_field(k) else None

    hrs = [h for r in records if (h := _hr(val(r, "heart_rate")))]
    alts = [a for r in records if (a := _num(val(r, "enhanced_altitude") if val(r, "enhanced_altitude") is not None else val(r, "altitude"))) is not None]
    times = [t for r in records if isinstance(t := val(r, "timestamp"), datetime)]
    if sessions:
        first = min(sessions, key=lambda s: val(s, "start_time") or datetime.max.replace(tzinfo=UTC))
        start = val(first, "start_time")
        dur = sum(_num(val(s, "total_elapsed_time")) or _num(val(s, "total_timer_time")) or 0 for s in sessions)
        dist = sum(_num(val(s, "total_distance")) or 0 for s in sessions)
        asc_vals = [_num(val(s, "total_ascent")) for s in sessions]
        ascent = sum(a for a in asc_vals if a) if any(asc_vals) else _ascent(alts)
        cal = sum(_num(val(s, "total_calories")) or 0 for s in sessions)
        avgs = [(_num(val(s, "avg_heart_rate")), _num(val(s, "total_elapsed_time")) or 1) for s in sessions if _num(val(s, "avg_heart_rate"))]
        avg_hr = sum(a * w for a, w in avgs) / sum(w for _, w in avgs) if avgs else None
        maxes = [m for s in sessions if (m := _num(val(s, "max_heart_rate")))]
        sport = map_sport(val(first, "sub_sport"), val(first, "sport"))
        name = val(first, "sport_profile_name")
    elif times:
        start, dur, name = min(times), (max(times) - min(times)).total_seconds(), None
        dist = max((_num(val(r, "distance")) or 0 for r in records), default=0)
        ascent, cal, avg_hr, maxes = _ascent(alts), 0, None, []
        sport = "other"
    else:
        raise ImportRejected("Ce fichier FIT ne contient pas d'activité (ni session ni enregistrements).")
    if not isinstance(start, datetime):
        raise ImportRejected("Date de début absente du fichier FIT.")
    return _row("fit", sport, start, dur, dist, ascent, hrs, avg_hr, max(maxes) if maxes else None, cal, name if isinstance(name, str) else None, str(val(first, "sport")) if sessions else None)


# ---------- XML (TCX, GPX) ----------

def _local(tag: Any) -> str:
    return tag.rsplit("}", 1)[-1] if isinstance(tag, str) else ""


def _kids(e: Element, name: str) -> list[Element]:
    return [c for c in e if _local(c.tag) == name]


def _first(e: Element, *path: str) -> Element | None:
    cur: Element | None = e
    for p in path:
        cur = next(iter(_kids(cur, p)), None) if cur is not None else None
    return cur


def _text(e: Element | None, *path: str) -> str | None:
    n = _first(e, *path) if e is not None else None
    return n.text.strip() if n is not None and n.text and n.text.strip() else None


def _fl(s: str | None) -> float | None:
    try:
        v = float(s) if s is not None else None
    except ValueError:
        return None
    return v if v is not None and math.isfinite(v) else None


def parse_tcx(root: Element) -> dict[str, Any]:
    act = next((a for acts in _kids(root, "Activities") for a in _kids(acts, "Activity")), None)
    if act is None:
        raise ImportRejected("Ce fichier TCX ne contient pas d'activité (peut-être un parcours ou un entraînement planifié).")
    laps = _kids(act, "Lap")
    start = _fmt_time(_text(act, "Id")) or (_fmt_time(laps[0].get("StartTime")) if laps else None)
    if start is None:
        raise ImportRejected("Date de début absente ou illisible dans le fichier TCX.")
    dur = sum(_fl(_text(lap, "TotalTimeSeconds")) or 0 for lap in laps)
    dist = sum(_fl(_text(lap, "DistanceMeters")) or 0 for lap in laps)
    cal = sum(_fl(_text(lap, "Calories")) or 0 for lap in laps)
    points = [p for lap in laps for t in _kids(lap, "Track") for p in _kids(t, "Trackpoint")]
    hrs = [h for p in points if (h := _hr(_text(p, "HeartRateBpm", "Value")))]
    alts = [a for p in points if (a := _fl(_text(p, "AltitudeMeters"))) is not None]
    times = [t for p in points if (t := _fmt_time(_text(p, "Time")))]
    if not dur and times:
        dur = (max(times) - min(times)).total_seconds()
    if not dist:  # laps sans distance (séance en salle) : distance cumulée des points s'ils en ont
        dist = max((d for p in points if (d := _fl(_text(p, "DistanceMeters"))) is not None), default=0)
    lap_avgs = [(a, _fl(_text(lap, "TotalTimeSeconds")) or 1) for lap in laps if (a := _hr(_text(lap, "AverageHeartRateBpm", "Value")))]
    avg_hr = sum(a * w for a, w in lap_avgs) / sum(w for _, w in lap_avgs) if lap_avgs else None
    maxes = [m for lap in laps if (m := _hr(_text(lap, "MaximumHeartRateBpm", "Value")))]
    sport_attr = act.get("Sport")
    return _row("tcx", map_sport(sport_attr), start, dur, dist, _ascent(alts), hrs, avg_hr, max(maxes) if maxes else None, cal, _text(act, "Notes"), (sport_attr or "").lower() or None)


def parse_gpx(root: Element) -> dict[str, Any]:
    trk = _kids(root, "trk")
    if not trk:
        raise ImportRejected("Ce fichier GPX ne contient pas de trace enregistrée (itinéraire ou points de passage seulement).")
    pts: list[tuple[datetime | None, float, float, float | None, int | None]] = []
    for t in trk:
        for seg in _kids(t, "trkseg"):
            for p in _kids(seg, "trkpt"):
                lat, lon = _fl(p.get("lat")), _fl(p.get("lon"))
                if lat is None or lon is None or not (-90 <= lat <= 90 and -180 <= lon <= 180):
                    continue
                hr = next((_hr(node.text) for node in p.iter() if _local(node.tag) in ("hr", "heartrate") and _hr(node.text)), None)
                pts.append((_fmt_time(_text(p, "time")), lat, lon, _fl(_text(p, "ele")), hr))
    timed = [p for p in pts if p[0] is not None]
    if len(timed) < 2:
        raise ImportRejected("Ce fichier GPX n'a pas d'horodatage : impossible de dater l'activité.")
    dist = sum(_haversine((a[1], a[2]), (b[1], b[2])) for a, b in zip(pts, pts[1:], strict=False))
    start, end = min(p[0] for p in timed), max(p[0] for p in timed)  # type: ignore[type-var]
    first = trk[0]
    sport = map_sport(_text(first, "type"), _text(first, "name"))
    return _row("gpx", sport, start, (end - start).total_seconds(), dist, _ascent([p[3] for p in pts if p[3] is not None]), [p[4] for p in pts if p[4]],
                None, None, None, _text(first, "name"), (_text(first, "type") or "").lower() or None)


def parse_xml(raw: bytes) -> dict[str, Any]:
    try:
        root = SafeET.fromstring(raw, forbid_dtd=True)
    except DefusedXmlException as e:
        raise ImportRejected("Contenu XML refusé (déclaration de type de document ou entités non autorisées).") from e
    except (ParseError, ValueError) as e:
        raise ImportRejected("Fichier XML illisible ou tronqué.") from e
    kind = _local(root.tag)
    if kind == "TrainingCenterDatabase":
        return parse_tcx(root)
    if kind == "gpx":
        return parse_gpx(root)
    raise ImportRejected("Format non reconnu : le fichier n'est ni FIT, ni TCX, ni GPX.")


# ---------- point d'entrée ----------

def parse_activity(raw: bytes, tz: Any = UTC) -> dict[str, Any]:
    """Octets -> ligne d'activité (`garmin_id` = « <format>:<empreinte> », début en heure locale `tz`). ImportRejected si inutilisable."""
    if not raw:
        raise ImportRejected("Fichier vide.")
    if len(raw) > MAX_FILE_BYTES:
        raise ImportRejected("Fichier trop volumineux (10 Mo maximum).")
    try:
        row = parse_fit(raw) if sniff(raw) == "fit" else parse_xml(raw)
    except ImportRejected:
        raise
    except Exception as e:  # noqa: BLE001 - un fichier hostile ne doit jamais produire une erreur 500
        raise ImportRejected("Fichier illisible.") from e
    local = row.pop("start_utc").astimezone(tz).replace(tzinfo=None, microsecond=0)
    row["day"], row["started_at"] = local.date(), local
    row["garmin_id"] = f"{row['source']}:{hashlib.sha256(raw).hexdigest()[:24]}"
    row["training_load"] = None
    return row


def is_duplicate(row: dict[str, Any], existing: list[dict[str, Any]]) -> bool:
    """Même identifiant (même fichier), ou même début à ± 2 min et durée proche (±10 %, au moins 1 min) : même séance déjà connue."""
    for a in existing:
        if a["garmin_id"] == row["garmin_id"]:
            return True
        if a.get("started_at") and abs((a["started_at"] - row["started_at"]).total_seconds()) <= 120:
            d1, d2 = a.get("duration_s") or 0, row["duration_s"]
            if abs(d1 - d2) <= max(60, 0.1 * max(d1, d2)):
                return True
    return False


def too_old(day: date, today: date, history_days: int) -> bool:
    return (today - day).days > history_days
