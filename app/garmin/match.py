"""Rapprochement séances planifiées <-> activités Garmin : même jour, même sport, durée la plus proche, une activité par séance."""
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
        merged["source"] = "garmin"
    return merged
