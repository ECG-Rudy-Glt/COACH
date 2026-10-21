"""Statistiques de progression : records, courbes par exercice, volume hebdomadaire, allure par sortie, trajectoire (règles ST6 à ST10).

Fonctions pures, sans entrée-sortie. Les trois sources de records (déclaré, mesuré par la montre, estimation de la montre) restent séparées (ST6) :
on ne fabrique jamais un record en extrapolant une sortie.
"""
from __future__ import annotations

from datetime import date, timedelta
from typing import Any

from app.plan import trajectory as T

EPLEY_MAX_REPS = 10  # au-delà, la formule d'Epley s'écarte trop de la réalité (ST7)
MAX_EXERCISES = 12
MIN_OUTINGS_FOR_CHANGE = 3
MIN_OUTING_KM = 3.0
RUN_DISTANCES = [("5 km", "bench.run_5k", 5.0, "race_5k"), ("10 km", "bench.run_10k", 10.0, "race_10k")]
RACE_METRICS = [(5.0, "race_5k"), (10.0, "race_10k"), (21.0975, "race_half")]


def _num(v: Any) -> float | None:
    return float(v) if isinstance(v, int | float) and not isinstance(v, bool) else None


def e1rm(kg: Any, reps: Any) -> float | None:
    """Maximum théorique sur une répétition (Epley), seulement pour 1 à 10 répétitions avec une charge (ST7)."""
    k, r = _num(kg), _num(reps)
    if k is None or r is None or k <= 0 or not 1 <= r <= EPLEY_MAX_REPS:
        return None
    return round(k * (1 + r / 30), 1)


def valid_sets(exercise: dict[str, Any]) -> list[dict[str, float | None]]:
    """Séries saisies utilisables : des répétitions positives, une charge facultative."""
    out = []
    for s in exercise.get("sets") or []:
        if not isinstance(s, dict):
            continue
        reps, kg = _num(s.get("reps")), _num(s.get("kg"))
        if reps and reps > 0 and (kg is None and s.get("kg") in (None, "") or kg is not None and kg >= 0):  # une charge illisible écarte la série
            out.append({"kg": kg, "reps": reps})
    return out


def _done_exercises(sessions: list[dict[str, Any]]) -> list[tuple[date, str, list[dict[str, float | None]]]]:
    rows = []
    for s in sorted((x for x in sessions if x["status"] == "done"), key=lambda x: x["day"]):
        for e in (s.get("logged") or {}).get("exercises") or []:
            sets = valid_sets(e) if isinstance(e, dict) else []
            if sets and isinstance(e.get("name"), str):
                rows.append((s["day"], e["name"][:80], sets))
    return rows


def exercise_curves(sessions: list[dict[str, Any]], since: date) -> list[dict[str, Any]]:
    """Une courbe par exercice : e1RM estimé quand il y a des charges (ST7), sinon meilleur nombre de répétitions. Un point par jour."""
    by: dict[str, dict[date, dict[str, Any]]] = {}
    for day, name, sets in _done_exercises(sessions):
        if day < since:
            continue
        pts = by.setdefault(name, {})
        best = max((e for s in sets if (e := e1rm(s["kg"], s["reps"])) is not None), default=None)
        cur = pts.setdefault(day, {"e1rm": None, "reps": 0.0, "kg": None, "sets": 0, "tonnage": 0.0})
        cur["e1rm"] = max(filter(None, [cur["e1rm"], best]), default=None)
        cur["reps"] = max(cur["reps"], max(s["reps"] for s in sets))
        cur["kg"] = max(filter(lambda v: v is not None, [cur["kg"], *[s["kg"] for s in sets]]), default=None)
        cur["sets"] += len(sets)
        cur["tonnage"] += sum(s["kg"] * s["reps"] for s in sets if s["kg"])
    out = []
    for name, pts in by.items():
        weighted = any(p["e1rm"] is not None for p in pts.values())
        points = [{"day": d.isoformat(), "value": round(p["e1rm"], 1) if weighted else p["reps"], "kg": p["kg"], "reps": p["reps"], "sets": p["sets"], "tonnage": round(p["tonnage"])}
                  for d, p in sorted(pts.items()) if (p["e1rm"] is not None or not weighted)]
        if not points:
            continue
        first, last = points[0]["value"], points[-1]["value"]
        out.append({"name": name, "mode": "e1rm" if weighted else "reps", "points": points, "sessions": len(pts),
                    "change": {"abs": round(last - first, 1), "pct": round((last - first) / first * 100, 1) if first else None} if len(points) >= 2 else None})
    return sorted(out, key=lambda x: (-x["sessions"], x["name"]))[:MAX_EXERCISES]


def lift_records(sessions: list[dict[str, Any]]) -> list[dict[str, Any]]:
    """Meilleures charges saisies par exercice : série la plus lourde et meilleur e1RM (ST7). Les exercices sans charge n'ont pas de record de charge."""
    best: dict[str, dict[str, Any]] = {}
    for day, name, sets in _done_exercises(sessions):
        for s in sets:
            if not s["kg"]:
                continue
            cur = best.setdefault(name, {"name": name, "kg": 0.0, "reps": 0, "day": day.isoformat(), "e1rm": None, "e1rm_day": None})
            if s["kg"] >= cur["kg"]:
                cur.update(kg=s["kg"], reps=s["reps"], day=day.isoformat())
            est = e1rm(s["kg"], s["reps"])
            if est is not None and (cur["e1rm"] is None or est >= cur["e1rm"]):
                cur.update(e1rm=est, e1rm_day=day.isoformat())
    return sorted(best.values(), key=lambda x: (x["e1rm"] is None, -(x["e1rm"] or 0), -x["kg"]))[:MAX_EXERCISES]


def declared_lifts(facts: dict[str, Any], catalog: dict[str, Any]) -> list[dict[str, Any]]:
    """Records et niveaux déclarés dans « Mes performances » pour les mouvements chargés."""
    out = []
    for key, raw in facts.items():
        b = catalog.get(key.removeprefix("bench."))
        if not key.startswith("bench.") or not b or b.kind != "weight_reps" or not isinstance(raw, dict):
            continue
        item: dict[str, Any] = {"label": b.label}
        for which in ("pr", "now"):
            r = raw.get(which)
            if isinstance(r, dict) and _num(r.get("weight")):
                item[which] = {"kg": r["weight"], "reps": r.get("reps") or 1, "e1rm": e1rm(r["weight"], r.get("reps") or 1), "year": r.get("year")}
        if "pr" in item or "now" in item:
            out.append(item)
    return out


def run_records(facts: dict[str, Any], activities: list[dict[str, Any]], metrics: list[dict[str, Any]]) -> list[dict[str, Any]]:
    """5 km et 10 km : record déclaré, meilleure allure mesurée sur une sortie d'au moins cette distance, dernière estimation de la montre (ST6)."""
    runs = [a for a in activities if a["sport"] == "run" and a["distance_m"] and a["duration_s"]]
    out = []
    for label, key, km, metric in RUN_DISTANCES:
        raw = facts.get(key) if isinstance(facts.get(key), dict) else {}
        declared = {w: {"time": raw[w].get("time"), "year": raw[w].get("year")} for w in ("pr", "now") if isinstance(raw.get(w), dict) and T.parse_time(raw[w].get("time"))}
        long = [a for a in runs if a["distance_m"] >= km * 1000]
        top = min(long, key=lambda a: a["duration_s"] / a["distance_m"], default=None)
        measured = {"km": round(top["distance_m"] / 1000, 1), "minutes": round(top["duration_s"] / 60), "pace": T.fmt_pace(top["duration_s"] / 60 / (top["distance_m"] / 1000)),
                    "day": top["day"].isoformat()} if top else None
        preds = sorted((m for m in metrics if m["metric"] == metric and m["value"]), key=lambda m: m["day"])
        watch = {"time": T.fmt_time(preds[-1]["value"] / 60), "day": preds[-1]["day"].isoformat()} if preds else None
        out.append({"label": label, "distance_km": km, "declared": declared, "measured": measured, "watch": watch, "outings": len(long)})
    return out


def weekly_volume(sessions: list[dict[str, Any]], activities: list[dict[str, Any]], today: date, weeks: int = 12) -> list[dict[str, Any]]:
    """Volume par semaine (lundi à dimanche) : minutes, kilomètres de course mesurés par la montre, séries et tonnage de musculation saisis (ST9)."""
    first = today - timedelta(days=today.weekday()) - timedelta(weeks=weeks - 1)
    out = []
    for i in range(weeks):
        mon = first + timedelta(weeks=i)
        end = mon + timedelta(days=7)
        acts = [a for a in activities if mon <= a["day"] < end]
        done = [s for s in sessions if s["status"] == "done" and mon <= s["day"] < end]
        manual = [s for s in done if not (s.get("logged") or {}).get("garmin_id")]
        sets = [x for s in done for e in (s.get("logged") or {}).get("exercises") or [] if isinstance(e, dict) for x in valid_sets(e)]
        out.append({"monday": mon.isoformat(), "current": mon <= today < end,
                    "minutes": round(sum((a["duration_s"] or 0) / 60 for a in acts) + sum(((s.get("logged") or {}).get("minutes") or s["duration_min"]) for s in manual)),
                    "run_km": round(sum(a["distance_m"] or 0 for a in acts if a["sport"] == "run") / 1000, 1),
                    "strength_sets": len(sets), "tonnage_kg": round(sum(x["kg"] * x["reps"] for x in sets if x["kg"]))})
    return out


def _window(runs: list[dict[str, Any]]) -> dict[str, Any] | None:
    if len(runs) < MIN_OUTINGS_FOR_CHANGE:
        return None
    km, sec = sum(a["distance_m"] for a in runs) / 1000, sum(a["duration_s"] for a in runs)
    return {"outings": len(runs), "pace": round(sec / 60 / km, 3), "pace_label": T.fmt_pace(sec / 60 / km)}


def pace_outings(activities: list[dict[str, Any]], today: date, days: int = 120) -> dict[str, Any]:
    """Allure de chaque sortie de course (ST10) et comparaison des 28 derniers jours aux 28 précédents, seulement avec assez de sorties de chaque côté."""
    runs = [a for a in activities if a["sport"] == "run" and (a["distance_m"] or 0) >= 1000 and a["duration_s"] and a["day"] <= today]
    outings = [{"day": a["day"].isoformat(), "km": round(a["distance_m"] / 1000, 1), "minutes": round(a["duration_s"] / 60), "pace": round(a["duration_s"] / 60 / (a["distance_m"] / 1000), 3),
                "pace_label": T.fmt_pace(a["duration_s"] / 60 / (a["distance_m"] / 1000)), "avg_hr": a["avg_hr"]}
               for a in sorted(runs, key=lambda a: a["day"]) if a["day"] >= today - timedelta(days=days - 1)]
    steady = [a for a in runs if a["distance_m"] >= MIN_OUTING_KM * 1000]
    recent = _window([a for a in steady if today - timedelta(days=27) <= a["day"]])
    before = _window([a for a in steady if today - timedelta(days=55) <= a["day"] < today - timedelta(days=27)])
    change = round((recent["pace"] - before["pace"]) * 60) if recent and before else None  # secondes par km, négatif = plus rapide
    return {"outings": outings, "recent": recent, "before": before, "change_s_per_km": change}


def trajectory_block(goals: list[dict[str, Any]], facts: dict[str, Any], metrics: list[dict[str, Any]], today: date) -> dict[str, Any] | None:
    """Trajectoire vers l'objectif de performance (C10 à C12, ST8) : phases et jalons du moteur, courbe de repère, estimations de la montre déjà mesurées."""
    target = T.pick_target(goals, today)
    desc = T.describe(target, facts, goals, today)
    if not target or not desc:
        return None
    km = target["distance_km"]
    level = T.current_level(facts, km)
    level_min = level[0] if level else None
    weeks = max((target["date"] - today).days // 7, 1)
    step = max(weeks // 12, 1)
    reference = [{"day": (today + timedelta(weeks=w)).isoformat(), "minutes": round(T.projected_minutes(target, level_min, today + timedelta(weeks=w), today), 2)}
                 for w in range(0, weeks + 1, step)] if level_min else []
    if reference and reference[-1]["day"] != target["date"].isoformat():
        reference.append({"day": target["date"].isoformat(), "minutes": target["time_min"]})
    src_km, metric = min(RACE_METRICS, key=lambda m: abs(m[0] - km))
    measured = [{"day": m["day"].isoformat(), "minutes": round(T.riegel(m["value"] / 60, src_km, km), 2)}
                for m in sorted(metrics, key=lambda m: m["day"]) if m["metric"] == metric and m["value"] and m["day"] >= today - timedelta(days=365)]
    return {**desc, "reference": reference, "measured": measured, "measured_source": metric if measured else None, "goal_minutes": target["time_min"]}
