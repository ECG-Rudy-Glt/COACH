"""Niveau actuel estimé à partir des données récentes (règles C14 et C15) : fonctions pures, sans entrée-sortie.

Un record est le meilleur résultat jamais obtenu, pas le niveau du moment (C13). Ce module cherche une meilleure information dans les sorties de course
mesurées par la montre (C14) et dans les charges saisies en séance (C15). Rien n'est écrit dans les faits de l'utilisateur : le résultat est ajouté en mémoire
aux faits (`with_estimates`) sous des clés `estimate.*`, et la saisie « actuel » de la page Mes performances reste prioritaire.
"""
from __future__ import annotations

from datetime import date, timedelta
from typing import Any

from app.plan import trajectory as T
from app.stats.progress import e1rm, valid_sets

RUN_WINDOW_DAYS = 56  # C14 : huit semaines
STRENGTH_WINDOW_DAYS = 84  # C15 : douze semaines
MIN_RUN_KM = 3.0
MAX_CLIMB_M_PER_KM = 15.0  # au-delà, l'allure ne dit rien de la vitesse à plat : sortie écartée plutôt que corrigée
PACE_RANGE = (2.5, 10.0)  # min/km : en dehors, marche ou erreur GPS
DISTANCE_RATIO = (1 / 3, 2.0)  # distance de la sortie / distance visée : au-delà, l'extrapolation de Riegel n'est plus défendable
SUSTAINED_HR = 0.85  # part de la FC max : effort soutenu (course ou test) ; en dessous de EASY_HR la sortie est un footing et ne dit rien du niveau
EASY_HR = 0.75
RUN_TYPES = {"running", "track_running", "trail_running"}  # tapis et course virtuelle : distance non fiable
BENCH_BY_NAME = {"bench press": "bench", "standing military press": "ohp", "barbell shoulder press": "ohp", "bent over barbell row": "row",
                 "barbell full squat": "squat", "leg press": "legpress"}  # exercices de référence du moteur (strength.CANDIDATES) -> id de « Mes performances »


def _hr_max(facts: dict[str, Any], activities: list[dict[str, Any]]) -> float | None:
    v = facts.get("running.hr_max")
    if isinstance(v, int | float) and not isinstance(v, bool) and v > 100:
        return float(v)
    seen = [a["max_hr"] for a in activities if a.get("max_hr")]
    return float(max(seen)) if len(seen) >= 5 else None


def run_estimate(activities: list[dict[str, Any]], today: date, to_km: float, hr_max: float | None = None) -> dict[str, Any] | None:
    """C14 : meilleur effort de course des huit dernières semaines, converti en temps équivalent sur `to_km` (Riegel, C10).

    Une sortie prouve seulement que l'on court « au moins aussi vite » : sans FC (ou avec une FC intermédiaire) le résultat est une borne (`bound`),
    un majorant du temps. Une sortie soutenue (FC moyenne >= 85 % de la FC max) donne une estimation ; un footing (< 75 %) est écarté.
    Estimations soutenues de plusieurs distances : on garde la plus lente (prudence). Elle ne dépasse jamais la meilleure borne trouvée.
    """
    lo, hi = max(MIN_RUN_KM, to_km * DISTANCE_RATIO[0]), to_km * DISTANCE_RATIO[1]
    sustained: dict[int, tuple[float, dict[str, Any]]] = {}  # meilleure estimation soutenue par tranche de distance
    bounds: list[tuple[float, dict[str, Any]]] = []
    for a in activities:
        km, sec = (a.get("distance_m") or 0) / 1000, a.get("duration_s") or 0
        if (a.get("type_key") not in RUN_TYPES or not sec or not lo <= km <= hi or not today - timedelta(days=RUN_WINDOW_DAYS) <= a["day"] <= today
                or (a.get("elevation_m") or 0) / km > MAX_CLIMB_M_PER_KM or not PACE_RANGE[0] <= sec / 60 / km <= PACE_RANGE[1]):
            continue
        share = a["avg_hr"] / hr_max if a.get("avg_hr") and hr_max else None
        if share is not None and share < EASY_HR:
            continue
        eq = T.riegel(sec / 60, km, to_km)
        info = {"km": round(km, 1), "minutes": sec / 60, "day": a["day"]}
        if share is None or share < SUSTAINED_HR:
            bounds.append((eq, info))
        else:
            band = 0 if km < 7.5 else 1 if km < 15 else 2
            if band not in sustained or eq < sustained[band][0]:
                sustained[band] = (eq, info)
    if not bounds and not sustained:
        return None
    if sustained:
        eq, info = max(sustained.values(), key=lambda b: b[0])
        kind = "estimate"
        if bounds and (tight := min(bounds, key=lambda b: b[0]))[0] < eq:  # une borne prouvée est plus rapide que l'estimation : le niveau ne peut pas être plus lent
            (eq, info), kind = tight, "bound"
    else:
        (eq, info), kind = min(bounds, key=lambda b: b[0]), "bound"
    return {"minutes": eq, "to_km": to_km, "from_km": info["km"], "from_time": T.fmt_time(info["minutes"]), "day": info["day"].isoformat(), "kind": kind,
            "outings": len(bounds) + len(sustained)}


def lift_estimates(sessions: list[dict[str, Any]], today: date) -> dict[str, dict[str, Any]]:
    """C15 : e1RM (Epley, 1 à 10 répétitions) le plus élevé des douze dernières semaines, par exercice de « Mes performances » (`bench` -> id).

    Seuls les exercices de référence du moteur sont reconnus, par leur nom ou par le mouvement noté dans le créneau de la séance. Les séries au-delà de
    10 répétitions et les séances non faites sont ignorées. Résultat marqué « estimé » : ce n'est ni une mesure ni la saisie de l'utilisateur.
    """
    out: dict[str, dict[str, Any]] = {}
    for s in sorted((x for x in sessions if x["status"] == "done" and today - timedelta(days=STRENGTH_WINDOW_DAYS) <= x["day"] <= today), key=lambda x: x["day"]):
        moves = {(sl.get("exercise") or {}).get("name"): sl.get("movement") for sl in (s.get("details") or {}).get("slots") or []}
        for e in (s.get("logged") or {}).get("exercises") or []:
            name = e.get("name") if isinstance(e, dict) else None
            bid = moves.get(name) or BENCH_BY_NAME.get(str(name).lower())
            if not bid:
                continue
            for st in valid_sets(e):
                est = e1rm(st["kg"], st["reps"]) if st["kg"] else None
                if est is not None and (bid not in out or est >= out[bid]["e1rm"]):
                    out[bid] = {"e1rm": est, "kg": st["kg"], "reps": int(st["reps"]), "day": s["day"].isoformat()}
    return out


def with_estimates(facts: dict[str, Any], activities: list[dict[str, Any]], sessions: list[dict[str, Any]], goals: list[dict[str, Any]], today: date) -> dict[str, Any]:
    """Copie des faits avec `estimate.run` (distance de l'objectif actif) et `estimate.bench.<id>`. Les faits saisis ne sont jamais modifiés."""
    out = dict(facts)
    target = T.pick_target(goals, today)
    est = run_estimate(activities, today, target["distance_km"], _hr_max(facts, activities)) if target else None
    if est:
        out["estimate.run"] = est
    for bid, v in lift_estimates(sessions, today).items():
        out[f"estimate.bench.{bid}"] = v
    return out
