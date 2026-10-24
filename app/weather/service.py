"""Réglages météo d'un utilisateur, perspective des 7 jours et résumé pour le coach. La météo propose, elle ne modifie jamais le plan."""
from datetime import date, timedelta
from typing import Any

from app.plan.engine import DAYS
from app.questionnaire.models import Fact, current_facts
from app.repo import Repo
from app.weather import client, rules

KEY_ENABLED, KEY_PLACE, KEY_HOUR = "ui.weather_enabled", "ui.weather_place", "ui.weather_hour"
HORIZON = 7
DISCLAIMER = "Prévision indicative, jamais un avis médical : c'est vous qui décidez de déplacer ou d'adapter la séance."


def settings(repo: Repo, user_id: int) -> dict[str, Any]:
    facts = current_facts(repo.list_facts(user_id))
    place = facts.get(KEY_PLACE) if isinstance(facts.get(KEY_PLACE), dict) else None
    hour = facts.get(KEY_HOUR)
    return {"server_enabled": client.server_enabled(), "place": place, "enabled": facts.get(KEY_ENABLED) is True and place is not None,
            "hour": hour if isinstance(hour, int) and 0 <= hour <= 23 else rules.DEFAULT_HOUR}


def save(repo: Repo, user_id: int, **values: Any) -> None:
    keys = {"enabled": KEY_ENABLED, "place": KEY_PLACE, "hour": KEY_HOUR}
    repo.add_facts(user_id, [Fact(key=keys[k], value=v, source="manual") for k, v in values.items()])


def set_place(repo: Repo, user_id: int, name: str, lat: float, lon: float) -> dict[str, Any]:
    """Enregistre la position ARRONDIE (0,1°) : la position saisie n'est jamais conservée telle quelle. Choisir une ville active la météo."""
    rlat, rlon = client.round_position(lat, lon)
    save(repo, user_id, place={"name": " ".join(name.split())[:60] or f"{rlat}, {rlon}", "lat": rlat, "lon": rlon}, enabled=True)
    return settings(repo, user_id)


def clear_place(repo: Repo, user_id: int) -> dict[str, Any]:
    save(repo, user_id, place=None, enabled=False)
    return settings(repo, user_id)


def _best_day(s: dict[str, Any], rows: list[dict[str, Any]], by_day: dict[str, dict[int, dict[str, Any]]], hour: int, today: date) -> dict[str, Any] | None:
    """Meilleur autre jour de la même semaine : météo « ok » au créneau, pas d'autre séance de plein air ou clé ce jour-là, et aucun avertissement
    d'espacement du déplacement existant (G5, I1, I2). Le plus proche gagne, à égalité le plus tardif."""
    from app.plan.api import move_warnings  # import local : app.plan.api ne dépend pas de la météo, mais reste chargé à la demande

    monday = s["day"] - timedelta(days=s["day"].weekday())
    best: tuple[int, int, date, dict[str, Any]] | None = None
    for i in range(7):
        d = monday + timedelta(days=i)
        if d == s["day"] or d < today or d > today + timedelta(days=HORIZON - 1):
            continue
        same = [r for r in rows if r["day"] == d and r["id"] != s["id"] and r["status"] != "skipped"]
        if any(r["kind"] in rules.OUTDOOR or r["kind"] in ("strength_lower", "strength_crossfit") for r in same):
            continue
        a = rules.assess(by_day.get(d.isoformat(), {}), hour, s["duration_min"])
        if not a or a["status"] != "ok":
            continue
        moved = {**s, "day": d}
        around = [r for r in rows if abs((r["day"] - d).days) < 2]
        if move_warnings(moved, around):
            continue
        cand = (abs((d - s["day"]).days), -d.toordinal(), d, a)
        if best is None or cand[:2] < best[:2]:
            best = cand
    return None if best is None else {"day": best[2].isoformat(), "weekday": DAYS[best[2].weekday()], "forecast": best[3]["forecast"]}


def outlook(repo: Repo, user_id: int, today: date) -> dict[str, Any]:
    st = settings(repo, user_id)
    base = {"server_enabled": st["server_enabled"], "enabled": st["enabled"] and st["server_enabled"], "place": (st["place"] or {}).get("name"), "hour": st["hour"], "items": [],
            "unavailable": False, "disclaimer": DISCLAIMER}
    if not base["enabled"]:
        return base
    fc = client.forecast(st["place"]["lat"], st["place"]["lon"])
    if fc is None:
        return {**base, "unavailable": True}  # échec silencieux : le plan reste utilisable
    rows = repo.list_sessions(user_id, today - timedelta(days=2), today + timedelta(days=HORIZON + 7))
    for s in sorted(rows, key=lambda r: (r["day"], r["id"])):
        if s["kind"] not in rules.OUTDOOR or s["status"] != "planned" or not today <= s["day"] < today + timedelta(days=HORIZON):
            continue
        a = rules.assess(fc.get(s["day"].isoformat(), {}), st["hour"], s["duration_min"])
        if a is None:
            continue
        suggestion = _best_day(s, rows, fc, st["hour"], today) if a["status"] != "ok" else None
        base["items"].append({"session_id": s["id"], "day": s["day"].isoformat(), "title": s["title"], "kind": s["kind"], "status": a["status"], "reasons": a["reasons"],
                              "forecast": a["forecast"], "suggestion": suggestion})
    return base


def coach_summary(repo: Repo, user_id: int, today: date) -> list[dict[str, Any]] | None:
    """Résumé météo de la semaine pour le contexte du coach ; None si la météo est désactivée ou indisponible (la clé n'apparaît alors pas)."""
    st = settings(repo, user_id)
    if not (st["enabled"] and st["server_enabled"]):
        return None
    o = outlook(repo, user_id, today)
    if o["unavailable"]:
        return None
    return [{"jour": i["day"], "seance": i["title"], "statut": i["status"], "regles": [r["rule"] for r in i["reasons"]],
             "resume": "; ".join(r["text"] for r in i["reasons"]) or "conditions correctes", "autre_jour_propose": (i["suggestion"] or {}).get("day")}
            for i in o["items"]]
