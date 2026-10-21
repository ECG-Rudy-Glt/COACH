"""Trajectoire vers un objectif de performance daté (ex. 10 km en moins de 40 min dans deux ans) : règles C10, C11, C12.

Le plan hebdomadaire ne voit que les 12 semaines qui précèdent un événement. La trajectoire couvre le reste : elle remonte le temps depuis
la date visée (affûtage, bloc spécifique, bloc seuil, puis base), estime le niveau actuel, dit si l'écart est raisonnable et fixe le volume
de course visé. Tout est déterministe : aucune valeur ne vient d'un LLM.
"""
from __future__ import annotations

from datetime import date, timedelta
from typing import Any

from app.plan.cycles import MACRO, target_phase

RIEGEL = 1.06  # C10 : t2 = t1 × (d2 / d1) ^ 1,06
MIN_KM, MAX_KM = 3.0, 21.2  # C11 : courses sur route de 3 km au semi ; au-delà, la trajectoire n'est pas définie
TEST_EVERY_WEEKS = 12  # C11 : un test chronométré tous les trois mois
BENCH_KM = {"bench.run_1k": 1.0, "bench.run_5k": 5.0, "bench.run_10k": 10.0, "bench.run_half": 21.0975}
# C12 : volume hebdomadaire de course visé (km) d'après le temps équivalent au 10 km ; repères de pratique, pas une loi.
VOLUME_STEPS = [(35.0, 65), (40.0, 50), (45.0, 40), (50.0, 32), (60.0, 25)]
VOLUME_DEFAULT = 20
ULTRA_CLEARANCE_WEEKS = 20  # C11 : un ultra ne se place pas dans les 20 semaines qui précèdent l'objectif de vitesse, ni juste après
ULTRA_RECOVERY_WEEKS = 3


def parse_time(v: Any) -> float | None:
    """« 45:30 » ou « 1:05:20 » -> minutes ; None si illisible."""
    if not isinstance(v, str):
        return None
    try:
        parts = [int(x) for x in v.strip().split(":")]
    except ValueError:
        return None
    if len(parts) == 2:
        parts = [0, *parts]
    if len(parts) != 3 or any(x < 0 for x in parts) or parts[1] > 59 or parts[2] > 59:
        return None
    total = parts[0] * 60 + parts[1] + parts[2] / 60
    return total if total > 0 else None


def riegel(minutes: float, from_km: float, to_km: float) -> float:
    return minutes * (to_km / from_km) ** RIEGEL


def fmt_time(minutes: float) -> str:
    s = round(minutes * 60)
    return f"{s // 3600}:{s % 3600 // 60:02d}:{s % 60:02d}" if s >= 3600 else f"{s // 60}:{s % 60:02d}"


def fmt_pace(min_per_km: float) -> str:
    s = round(min_per_km * 60)
    return f"{s // 60}:{s % 60:02d}"


def current_level(facts: dict[str, Any], to_km: float) -> tuple[float, str] | None:
    """Temps équivalent sur `to_km` d'après les records de course (C10). Le niveau actuel (« now ») prime sur le record.

    En cas de doute on garde l'équivalent le plus lent : un record ancien ou une formule optimiste ne doivent pas rendre l'objectif trop proche.
    """
    found: list[tuple[float, str]] = []
    for key, km in BENCH_KM.items():
        raw = facts.get(key)
        if not isinstance(raw, dict):
            continue
        rec = raw.get("now") or raw.get("pr") or {}
        minutes = parse_time(rec.get("time")) if isinstance(rec, dict) else None
        if minutes:
            found.append((riegel(minutes, km, to_km), f"{key.removeprefix('bench.run_').replace('half', 'semi')} en {fmt_time(minutes)}"))
    return max(found) if found else None


def level_is_record_only(facts: dict[str, Any], to_km: float) -> bool:
    """C13 : vrai si le niveau retenu par C10 vient d'un record seul. Un record est le meilleur temps jamais couru, pas le niveau du moment."""
    best: tuple[float, bool] | None = None
    for key, km in BENCH_KM.items():
        raw = facts.get(key)
        if not isinstance(raw, dict):
            continue
        now = parse_time((raw.get("now") or {}).get("time")) if isinstance(raw.get("now"), dict) else None
        rec = now or (parse_time((raw.get("pr") or {}).get("time")) if isinstance(raw.get("pr"), dict) else None)
        if rec and (best is None or riegel(rec, km, to_km) > best[0]):
            best = (riegel(rec, km, to_km), not now)
    return bool(best and best[1])


def volume_target_km(goal_minutes: float, goal_km: float) -> int:
    """Volume hebdomadaire visé (C12), d'après le temps de l'objectif ramené au 10 km."""
    t10 = riegel(goal_minutes, goal_km, 10.0)
    return next((km for limit, km in VOLUME_STEPS if t10 <= limit), VOLUME_DEFAULT)


def pick_target(goals: list[dict[str, Any]], today: date) -> dict[str, Any] | None:
    """Objectif de performance actif et daté : distance de course et temps visé (details.distance_km, target_value, unit)."""
    found = []
    for g in goals:
        if g["status"] != "active" or g["kind"] != "performance" or not g.get("target_date") or g["target_date"] < today:
            continue
        d = g.get("details") or {}
        km, value = d.get("distance_km"), d.get("target_value")
        if not all(isinstance(x, int | float) and not isinstance(x, bool) for x in (km, value)) or not MIN_KM <= km <= MAX_KM or value <= 0:
            continue
        unit = str(d.get("unit") or "min").lower()
        minutes = float(value) / 60 if unit in ("s", "sec") else float(value) * 60 if unit in ("h", "heure", "heures") else float(value)
        if unit not in ("min", "s", "sec", "h", "heure", "heures"):
            continue
        found.append(({"principal": 0, "important": 1}.get(g["priority"], 2), g["target_date"],
                      {"date": g["target_date"], "title": g["title"], "distance_km": float(km), "time_min": minutes}))
    return min(found, key=lambda x: (x[0], x[1]))[2] if found else None


def monday_of(d: date) -> date:
    return d - timedelta(days=d.weekday())


def weeks_between(monday: date, target: date) -> int:
    return max(0, (monday_of(target) - monday_of(monday)).days // 7)


def projected_minutes(target: dict[str, Any], level_min: float | None, monday: date, today: date) -> float:
    """Temps projeté sur la distance de l'objectif à `monday` : interpolation linéaire entre le niveau actuel et le temps visé (repère, pas une prévision)."""
    goal = target["time_min"]
    if level_min is None or level_min <= goal:
        return goal
    span = max((target["date"] - today).days, 1)
    share = min(max((monday - today).days / span, 0.0), 1.0)
    return level_min - (level_min - goal) * share


def pace_10k_equivalent(target: dict[str, Any], level_min: float | None, monday: date, today: date) -> float:
    """Allure (min/km) au 10 km équivalente, projetée à `monday`."""
    t = projected_minutes(target, level_min, monday, today)
    return riegel(t, target["distance_km"], 10.0) / 10.0


def quality_session(macro: str, q_min: int, target: dict[str, Any] | None, level_min: float | None, monday: date, today: date) -> dict[str, str] | None:
    """Séance de qualité de la phase seuil ou spécifique ; None dans les autres phases. La durée vient du volume de la semaine (échauffement et retour au calme inclus)."""
    if macro not in ("threshold", "specific") or not target:
        return None
    work = max(q_min - 15, 0)  # 15 min d'échauffement et de retour au calme
    if macro == "threshold":
        pace = pace_10k_equivalent(target, level_min, monday, today) * 1.04  # même convention que les zones : seuil ≈ allure 10 km × 1,04
        n = max(2, min(4, work // 10))  # au plus 4 × 8 min : 32 min au seuil
        return {"format": f"{n} × 8 min à allure seuil (≈ {fmt_pace(pace)}/km), 2 min de trot", "pace": fmt_pace(pace)}
    pace = projected_minutes(target, level_min, monday, today) / target["distance_km"]
    n = max(3, min(6, work // 6))  # au plus 6 × 1 000 m
    return {"format": f"{n} × 1 000 m à l'allure de l'objectif (≈ {fmt_pace(pace)}/km), 90 s de trot", "pace": fmt_pace(pace)}


def is_ultra(g: dict[str, Any]) -> bool:
    d = g.get("details") or {}
    km = d.get("distance_km")
    return g["kind"] == "event" and (("ultra" in g["title"].lower()) or (isinstance(km, int | float) and km > 42.2))


def describe(target: dict[str, Any] | None, facts: dict[str, Any], goals: list[dict[str, Any]], today: date) -> dict[str, Any] | None:
    """Trajectoire complète pour l'écran et le coach IA : niveau, écart, phases, jalons, avertissements."""
    if not target:
        return None
    km, goal = target["distance_km"], target["time_min"]
    level = current_level(facts, km)
    level_min = level[0] if level else None
    this = monday_of(today)
    end = monday_of(target["date"])
    # phases : semaine par semaine, regroupées
    phases: list[dict[str, Any]] = []
    w = 0
    while this + timedelta(weeks=w) <= end:
        monday = this + timedelta(weeks=w)
        macro = target_phase(weeks_between(monday, target["date"]))
        if phases and phases[-1]["macro"] == macro:
            phases[-1]["weeks"] += 1
            phases[-1]["end"] = (monday + timedelta(days=6)).isoformat()
        else:
            phases.append({"macro": macro, "label": MACRO[macro][0], "text": MACRO[macro][1], "start": monday.isoformat(),
                           "end": (monday + timedelta(days=6)).isoformat(), "weeks": 1})
        w += 1
    weeks_left = max(weeks_between(this, target["date"]), 1)
    gap = (level_min - goal) / level_min if level_min and level_min > goal else 0.0
    per_month = gap * 100 / max(weeks_left / 4.345, 1.0)
    # C11 : gain mensuel jugé raisonnable (repère de pratique) : ≤ 0,8 % ambitieux au-delà de 1,5 % très ambitieux
    verdict = "atteint" if level_min is not None and level_min <= goal else "inconnu" if level_min is None else \
        "réaliste" if per_month <= 0.8 else "ambitieux" if per_month <= 1.5 else "très ambitieux"
    pace_goal = goal / km
    ceiling = volume_target_km(goal, km)
    test_km = 5.0 if km >= 8 else 3.0
    milestones = []
    k = TEST_EVERY_WEEKS
    while k < weeks_left - 1 and level_min is not None:
        monday = this + timedelta(weeks=k)
        milestones.append({"date": monday.isoformat(), "label": f"Test {test_km:g} km",
                           "target_time": fmt_time(riegel(projected_minutes(target, level_min, monday, today), km, test_km))})
        k += TEST_EVERY_WEEKS
    warnings = []
    lo, hi = end - timedelta(weeks=ULTRA_CLEARANCE_WEEKS), end + timedelta(weeks=ULTRA_RECOVERY_WEEKS)
    for g in goals:
        if g["status"] != "active" or not is_ultra(g):
            continue
        if not g.get("target_date"):
            warnings.append(f"« {g['title']} » n'a pas de date : le plan ne le prend pas encore en compte. Pour ne pas gêner le travail de vitesse, "
                            f"placez-le au moins {ULTRA_CLEARANCE_WEEKS} semaines avant le {target['date'].strftime('%d/%m/%Y')} ou après.")
        elif lo <= g["target_date"] <= hi:
            warnings.append(f"« {g['title']} » ({g['target_date'].strftime('%d/%m/%Y')}) tombe dans les {ULTRA_CLEARANCE_WEEKS} semaines qui précèdent l'objectif "
                            "ou juste après : le volume d'ultra et le travail de vitesse se gênent. Déplacez l'un des deux.")
    if verdict in ("ambitieux", "très ambitieux"):
        warnings.append(f"Il faut gagner {gap * 100:.0f} % sur {weeks_left} semaines ({per_month:.2f} % par mois) : "
                        + ("c'est ambitieux, le plan reste prudent et un test tous les trois mois dira si vous êtes dans la trajectoire." if verdict == "ambitieux"
                           else "c'est très ambitieux, mieux vaut repousser la date ou viser un temps plus lent."))
    return {
        "target": {"title": target["title"], "date": target["date"].isoformat(), "distance_km": km, "time": fmt_time(goal), "pace": fmt_pace(pace_goal)},
        "level": {"time": fmt_time(level_min), "source": level[1], "record_only": level_is_record_only(facts, km)} if level else None,
        "gap_pct": round(gap * 100, 1), "per_month_pct": round(per_month, 2), "verdict": verdict,
        "weekly_km_target": ceiling, "weeks_left": weeks_left, "phases": phases, "milestones": milestones, "warnings": warnings,
        "current_phase": phases[0]["macro"] if phases else None,
    }
