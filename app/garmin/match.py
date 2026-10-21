"""Rapprochement séances planifiées <-> activités Garmin : même jour, même sport, durée la plus proche, une activité par séance."""
from datetime import date, timedelta
from typing import Any

MIN_MINUTES = 10  # en dessous, ce n'est pas une séance (échauffement enregistré à part, pause…)
COMPAT = {"run": "run_", "strength": "strength_"}  # sport Garmin -> préfixe de type de séance


def _planned_min(s: dict[str, Any]) -> float:
    return float(s.get("duration_min") or 0)


def pair_up(sessions: list[dict[str, Any]], activities: list[dict[str, Any]]) -> list[tuple[dict[str, Any], dict[str, Any]]]:
    """Couples (séance, activité). Les séances déjà reliées à une activité et les activités déjà utilisées sont ignorées."""
    used = {(s.get("logged") or {}).get("garmin_id") for s in sessions} - {None}
    free = [s for s in sessions if not (s.get("logged") or {}).get("garmin_id") and s["status"] != "skipped"]
    cands = []
    for a in activities:
        prefix = COMPAT.get(a["sport"])
        if not prefix or a["garmin_id"] in used or (a["duration_s"] or 0) < MIN_MINUTES * 60:
            continue
        for s in free:
            if s["day"] == a["day"] and s["kind"].startswith(prefix):
                cands.append((abs(_planned_min(s) - (a["duration_s"] or 0) / 60), s["id"], a["garmin_id"], s, a))
    out, taken_s, taken_a = [], set(), set()
    for _, sid, gid, s, a in sorted(cands, key=lambda c: c[:3]):
        if sid not in taken_s and gid not in taken_a:
            taken_s.add(sid)
            taken_a.add(gid)
            out.append((s, a))
    return out


def link_fields(s: dict[str, Any], a: dict[str, Any]) -> dict[str, Any]:
    """Champs Garmin ajoutés au retour de séance, sans jamais écraser ce que l'utilisateur a saisi."""
    cur = s.get("logged") or {}
    fields = {"garmin_id": a["garmin_id"], "avg_hr": a.get("avg_hr"), "max_hr": a.get("max_hr"), "calories": a.get("calories"),
              "training_load": round(a["training_load"]) if a.get("training_load") else None, "garmin_name": a.get("name")}
    if a.get("distance_m"):
        fields["distance_km"] = round(a["distance_m"] / 1000, 1)
    fields["minutes"] = round((a["duration_s"] or 0) / 60)
    merged = {**cur}
    for k, v in fields.items():
        if v is not None and merged.get(k) in (None, ""):
            merged[k] = v
    merged["garmin_id"] = a["garmin_id"]
    if s["status"] == "planned" and "source" not in merged:
        merged["source"] = a.get("source") or "garmin"
    return merged


GARMIN_FIELDS = ("garmin_id", "garmin_name", "avg_hr", "max_hr", "calories", "training_load", "distance_km")
LOOKBACK_DAYS = 28
SUGGEST_DAYS = 3  # une séance faite un autre jour : proposée si l'écart ne dépasse pas 3 jours


def unlink_fields(logged: dict[str, Any] | None) -> dict[str, Any]:
    """Retour de séance sans les champs venus de la montre (ce que l'utilisateur a saisi reste)."""
    out = {k: v for k, v in (logged or {}).items() if k not in GARMIN_FIELDS}
    if out.get("source") in ("garmin", "fit", "tcx", "gpx"):
        del out["source"]
    return out


def compatible(session: dict[str, Any], activity: dict[str, Any]) -> bool:
    prefix = COMPAT.get(activity["sport"])
    return bool(prefix) and session["kind"].startswith(prefix)


def suggestions(activity: dict[str, Any], sessions: list[dict[str, Any]], limit: int = 4) -> list[dict[str, Any]]:
    """Séances auxquelles rapprocher une activité : du même sport, non encore reliées, à 3 jours près ; le jour d'abord, puis la durée."""
    minutes = (activity["duration_s"] or 0) / 60
    out = []
    for s in sessions:
        gap = abs((s["day"] - activity["day"]).days)
        if (s.get("logged") or {}).get("garmin_id") or s["status"] == "skipped" or gap > SUGGEST_DAYS or not compatible(s, activity):
            continue
        out.append((gap, abs(_planned_min(s) - minutes), s["id"], {"id": s["id"], "title": s["title"], "day": s["day"].isoformat(), "status": s["status"],
                                                                  "duration_min": s["duration_min"]}))
    return [x[3] for x in sorted(out, key=lambda x: x[:3])[:limit]]


def _link(repo: Any, user_id: int, s: dict[str, Any], a: dict[str, Any]) -> None:
    repo.update_session(user_id, s["id"], "done" if s["status"] == "planned" else s["status"], link_fields(s, a))


def auto_link(repo: Any, user_id: int, today: date, days: int = LOOKBACK_DAYS) -> int:
    """Relie les activités Garmin des dernières semaines aux séances : même jour d'abord (séance planifiée ou déjà saisie à la main), puis l'activité
    faite le lendemain d'une séance restée « planifiée ». Une activité ne sert qu'une séance, une séance qu'une activité ; rien n'est jamais écrasé."""
    start = today - timedelta(days=days)
    acts = [a for a in repo.list_activities(user_id, start, 1000) if a["day"] <= today]
    if not acts:
        return 0
    window = repo.list_sessions(user_id, start - timedelta(days=2), today + timedelta(days=1))
    linked = 0
    for s, a in pair_up(window, acts):
        _link(repo, user_id, s, a)
        s["status"], s["logged"] = ("done" if s["status"] == "planned" else s["status"]), link_fields(s, a)
        linked += 1
    used = {(s.get("logged") or {}).get("garmin_id") for s in window} - {None}
    for a in sorted(acts, key=lambda x: (x["day"], x["garmin_id"])):
        prefix = COMPAT.get(a["sport"])
        if not prefix or (a["duration_s"] or 0) < 15 * 60 or a["garmin_id"] in used:  # les trajets très courts ne sont pas des séances
            continue
        cands = [s for s in window if s["status"] == "planned" and not (s.get("logged") or {}).get("garmin_id") and s["kind"].startswith(prefix)
                 and 0 <= (a["day"] - s["day"]).days <= 1]
        cands.sort(key=lambda s: ((a["day"] - s["day"]).days, s["id"]))  # le jour même d'abord, puis la veille
        if cands:
            _link(repo, user_id, cands[0], a)
            cands[0]["status"], cands[0]["logged"] = "done", link_fields(cands[0], a)
            used.add(a["garmin_id"])
            linked += 1
    return linked
