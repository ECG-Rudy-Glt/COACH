"""Statistiques du quotidien : pas, repas face aux cibles, poids, activité récente (règles ST1 à ST5).

Fonctions pures : elles reçoivent les lignes déjà lues en base et ne font aucune entrée-sortie. Rien n'est inventé : une donnée absente reste
absente (None), jamais 0 ni une valeur interpolée (ST1).
"""
from __future__ import annotations

from datetime import date, timedelta
from typing import Any

from app.nutrition.engine import KIND_SPORT

MIN_RUN_KM_FOR_PACE = 1.0  # en dessous, l'allure n'a pas de sens (échauffement, GPS)
RECENT_LIMIT = 8


def last_days(today: date, n: int = 7) -> list[date]:
    """Les `n` derniers jours, du plus ancien à aujourd'hui."""
    return [today - timedelta(days=n - 1 - i) for i in range(n)]


def steps_block(rows: list[dict[str, Any]], today: date, connected: bool) -> dict[str, Any]:
    """Pas par jour sur 7 jours (ST4). Aujourd'hui est incomplet : il est affiché mais n'entre pas dans la moyenne."""
    by_day = {r["day"]: int(r["value"]) for r in rows if r["metric"] == "steps" and r["value"] is not None}
    days = [{"day": d.isoformat(), "steps": by_day.get(d)} for d in last_days(today)]
    complete = [x["steps"] for x in days if x["steps"] is not None and x["day"] != today.isoformat()]
    return {"connected": connected, "days": days, "average": round(sum(complete) / len(complete)) if complete else None, "days_measured": len(complete),
            "today_partial": True}


def nutrition_block(meals: list[dict[str, Any]], today: date, targets: dict[date, dict[str, Any]] | None) -> dict[str, Any]:
    """Énergie et protéines estimées par jour face à la cible (ST2). Un jour sans repas estimé n'a pas de valeur et ne compte pas dans la moyenne.

    `targets` : cible par jour, ou None quand le profil est trop incomplet pour qu'une cible ait un sens (ST1).
    """
    out = []
    for d in last_days(today):
        done = [m["analysis"] for m in meals if m["day"] == d and m["analysis"]]
        tg = (targets or {}).get(d)
        out.append({"day": d.isoformat(), "meals": sum(1 for m in meals if m["day"] == d), "estimated_meals": len(done),
                    "kcal": round(sum(a["kcal"] for a in done)) if done else None, "protein_g": round(sum(a["protein_g"] for a in done)) if done else None,
                    "target_kcal": tg["kcal"] if tg else None, "target_protein_g": tg["protein_g"] if tg else None})
    est = [x for x in out if x["kcal"] is not None]
    avg = None
    if est:
        tk = [x["target_kcal"] for x in est if x["target_kcal"] is not None]
        tp = [x["target_protein_g"] for x in est if x["target_protein_g"] is not None]
        avg = {"kcal": round(sum(x["kcal"] for x in est) / len(est)), "protein_g": round(sum(x["protein_g"] for x in est) / len(est)),
               "target_kcal": round(sum(tk) / len(tk)) if tk else None, "target_protein_g": round(sum(tp) / len(tp)) if tp else None, "days": len(est)}
    return {"days": out, "average": avg, "has_target": bool(targets)}


def weight_block(trend: dict[str, Any], target_kg: float | None) -> dict[str, Any]:
    """Courbe de poids avec moyenne glissante de 7 jours (ST3 / N5). Le rythme n'est donné que si le moteur a assez de pesées."""
    return {"series": trend["series"][-60:], "current": trend.get("current"), "rate_pct_per_week": trend.get("rate_pct_per_week"), "target_kg": target_kg}


def _pace(distance_m: float | None, duration_s: int | None) -> float | None:
    if not distance_m or not duration_s or distance_m < MIN_RUN_KM_FOR_PACE * 1000:
        return None
    return round(duration_s / 60 / (distance_m / 1000), 2)


def recent_items(activities: list[dict[str, Any]], sessions: list[dict[str, Any]], today: date, days: int = 14) -> list[dict[str, Any]]:
    """Activités récentes : celles de la montre, plus les séances validées à la main (une séance reliée à la montre est déjà dans les activités)."""
    since = today - timedelta(days=days - 1)
    items: list[dict[str, Any]] = []
    for a in activities:
        if since <= a["day"] <= today:
            items.append({"day": a["day"].isoformat(), "source": "montre", "sport": a["sport"], "title": a["name"] or a["type_key"] or a["sport"],
                          "minutes": round((a["duration_s"] or 0) / 60) or None, "distance_km": round(a["distance_m"] / 1000, 1) if a["distance_m"] else None,
                          "pace_min_km": _pace(a["distance_m"], a["duration_s"]) if a["sport"] == "run" else None, "avg_hr": a["avg_hr"]})
    for s in sessions:
        lg = s.get("logged") or {}
        if s["status"] != "done" or lg.get("garmin_id") or not since <= s["day"] <= today:
            continue
        items.append({"day": s["day"].isoformat(), "source": "saisie", "sport": KIND_SPORT.get(s["kind"], "other"), "title": s["title"],
                      "minutes": lg.get("minutes") or s["duration_min"], "distance_km": lg.get("distance_km"), "pace_min_km": None, "avg_hr": lg.get("avg_hr")})
    return sorted(items, key=lambda x: x["day"], reverse=True)[:RECENT_LIMIT]


def week_block(sessions: list[dict[str, Any]], activities: list[dict[str, Any]], today: date) -> dict[str, Any]:
    """Semaine en cours (lundi à dimanche) : séances faites sur séances prévues, minutes et kilomètres de course mesurés ou saisis."""
    monday = today - timedelta(days=today.weekday())
    week = [s for s in sessions if monday <= s["day"] < monday + timedelta(days=7) and s["status"] != "skipped"]
    done = [s for s in week if s["status"] == "done"]
    acts = [a for a in activities if monday <= a["day"] <= today]
    manual_min = sum(((s.get("logged") or {}).get("minutes") or s["duration_min"]) for s in done if not (s.get("logged") or {}).get("garmin_id"))
    return {"monday": monday.isoformat(), "planned": len(week), "done": len(done), "minutes": round(sum((a["duration_s"] or 0) / 60 for a in acts) + manual_min),
            "run_km": round(sum((a["distance_m"] or 0) for a in acts if a["sport"] == "run") / 1000, 1)}
