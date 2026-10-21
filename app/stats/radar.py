"""Araignée de forme : quatre axes, chacun mesuré par une donnée stockée (règles ST14 à ST20).

Fonctions pures, sans entrée-sortie. Chaque axe est un pourcentage de TA PROPRE référence (objectif du plan, temps visé, meilleure période précédente),
plafonné à 100 : aucune comparaison avec d'autres personnes, aucune table de seuils, aucun score global. Un axe sans donnée suffisante n'est pas calculé
et dit pourquoi (`reason`). La vitesse et la récupération ne sont pas des axes : aucune mesure validée n'existe pour elles (ST14).
"""
from __future__ import annotations

from datetime import date, timedelta
from typing import Any

from app.plan import level as L
from app.plan import trajectory as T
from app.stats import progress, regularity

AXES = ("volume", "regularity", "endurance", "strength")
NOT_MEASURED = ("speed", "recovery")
COMPARE_WEEKS = 4  # « il y a 4 semaines » (ST20)
MIN_AXES = 3  # en dessous, un polygone ne dit rien : on affiche les axes en texte (ST14)

VOLUME_WEEKS = 4  # moyenne des 4 dernières semaines terminées (ST16)
VOLUME_REF_WEEKS = 12
VOLUME_MIN_REF_WEEKS = 3  # semaines non vides nécessaires pour que « ma meilleure semaine » ait un sens
VOLUME_RUNNER_WEEKS = 4  # semaines de course sur les 16 dernières pour compter en kilomètres plutôt qu'en minutes

REG_WEEKS = 12  # ST17
REG_MIN_WEEKS = 4
REG_MIN_SESSIONS = 8

ENDURANCE_FALLBACK_KM = 10.0  # sans objectif de performance
ENDURANCE_REF_AGES = range(9, 21)  # ST18 : fenêtres de 8 semaines qui se terminent 9 à 20 semaines avant, donc sans recouvrement avec la fenêtre actuelle

STRENGTH_MIN_LIFTS = 2  # ST19


def _pct(value: float, reference: float) -> int:
    """Pourcentage de la référence, plafonné à 100 (ST15)."""
    return min(100, round(value / reference * 100)) if reference > 0 else 0


def _span(rows: list[dict[str, Any]]) -> dict[str, str]:
    return {"from": rows[0]["monday"], "to": (date.fromisoformat(rows[-1]["monday"]) + timedelta(days=6)).isoformat()}


def _delta(now: dict[str, Any] | None, before: dict[str, Any] | None) -> int | None:
    return now["score"] - before["score"] if now and before else None


# ---------- volume (ST16) ----------

def _volume_at(rows: list[dict[str, Any]], back: int, key: str, km_target: int | None) -> dict[str, Any] | None:
    """Moyenne des 4 semaines terminées qui se terminent `back` semaines avant la dernière, face à la référence (objectif du plan ou meilleure semaine)."""
    end = len(rows) - back
    window, pool = rows[end - VOLUME_WEEKS:end], rows[max(end - VOLUME_WEEKS - VOLUME_REF_WEEKS, 0):end - VOLUME_WEEKS]
    if len(window) < VOLUME_WEEKS:
        return None
    if key == "run_km" and km_target:
        ref, kind = float(km_target), "goal"
    else:
        used = [r[key] for r in pool if r[key] > 0]
        if len(used) < VOLUME_MIN_REF_WEEKS:
            return None
        ref, kind = float(max(used)), "best"
    value = sum(r[key] for r in window) / VOLUME_WEEKS
    return {"score": _pct(value, ref), "value": round(value, 1), "reference": round(ref, 1), "reference_kind": kind, "weeks": [r[key] for r in window], **_span(window)}


def volume_axis(weeks: list[dict[str, Any]], km_target: int | None) -> dict[str, Any]:
    """`weeks` : lignes de `progress.weekly_volume`, la dernière est la semaine en cours (incomplète, exclue)."""
    rows = weeks[:-1]
    runner = sum(1 for r in rows[-16:] if r["run_km"] > 0) >= VOLUME_RUNNER_WEEKS
    key = "run_km" if runner else "minutes"
    now = _volume_at(rows, 0, key, km_target)
    before = _volume_at(rows, COMPARE_WEEKS, key, km_target)
    return {"id": "volume", "status": "ok" if now else "insufficient", "reason": None if now else "short_history", "unit": "km" if runner else "min", "now": now, "before": before,
            "delta": _delta(now, before)}


# ---------- régularité (ST17) ----------

def _regularity_at(rows: list[dict[str, Any]], back: int) -> dict[str, Any] | None:
    end = len(rows) - back
    window = rows[end - REG_WEEKS:end]
    planned, done = sum(r["planned"] for r in window), sum(r["done"] for r in window)
    weeks = sum(1 for r in window if r["planned"] > 0)
    if len(window) < REG_WEEKS or weeks < REG_MIN_WEEKS or planned < REG_MIN_SESSIONS:
        return None
    return {"score": _pct(done, planned), "done": done, "planned": planned, "weeks": weeks, **_span(window)}


def regularity_axis(sessions: list[dict[str, Any]], today: date, enabled: bool) -> dict[str, Any]:
    if not enabled:  # ST13 : désactivée dans le profil, rien n'est calculé
        return {"id": "regularity", "status": "off", "reason": "off", "now": None, "before": None, "delta": None}
    rows = regularity.week_rows(sessions, today, weeks=REG_WEEKS + COMPARE_WEEKS + 1)[:-1]  # la semaine en cours est exclue
    now, before = _regularity_at(rows, 0), _regularity_at(rows, COMPARE_WEEKS)
    return {"id": "regularity", "status": "ok" if now else "insufficient", "reason": None if now else "few_planned", "now": now, "before": before, "delta": _delta(now, before)}


# ---------- endurance (ST18) ----------

def _endurance_at(activities: list[dict[str, Any]], today: date, to_km: float, hr_max: float | None, goal_min: float | None) -> tuple[dict[str, Any] | None, str | None]:
    est = L.run_estimate(activities, today, to_km, hr_max)
    if not est:
        return None, "no_run"
    if goal_min:
        ref, kind, ref_day = goal_min, "goal", None
    else:
        past = [e for age in ENDURANCE_REF_AGES if (e := L.run_estimate(activities, today - timedelta(weeks=age), to_km, hr_max))]
        best = min(past, key=lambda e: e["minutes"], default=None)
        if not best:
            return None, "no_reference"
        ref, kind, ref_day = best["minutes"], "best", best["day"]
    return {"score": _pct(ref, est["minutes"]), "minutes": round(est["minutes"], 2), "time": T.fmt_time(est["minutes"]), "to_km": to_km, "kind": est["kind"], "from_km": est["from_km"],
            "from_time": est["from_time"], "day": est["day"], "outings": est["outings"], "reference_minutes": round(ref, 2), "reference_time": T.fmt_time(ref),
            "reference_kind": kind, "reference_day": ref_day}, None


def endurance_axis(activities: list[dict[str, Any]], facts: dict[str, Any], goals: list[dict[str, Any]], today: date) -> dict[str, Any]:
    target = T.pick_target(goals, today)
    to_km = target["distance_km"] if target else ENDURANCE_FALLBACK_KM
    goal_min = target["time_min"] if target else None
    hr_max = L._hr_max(facts, activities)
    now, reason = _endurance_at(activities, today, to_km, hr_max, goal_min)
    before, _ = _endurance_at(activities, today - timedelta(weeks=COMPARE_WEEKS), to_km, hr_max, goal_min) if now else (None, None)
    return {"id": "endurance", "status": "ok" if now else "insufficient", "reason": reason, "now": now, "before": before, "delta": _delta(now, before)}


# ---------- force (ST19) ----------

def _strength_at(sessions: list[dict[str, Any]], today: date, labels: dict[str, str]) -> dict[str, Any] | None:
    current = L.lift_estimates(sessions, today)
    earlier = L.lift_estimates(sessions, today - timedelta(days=L.STRENGTH_WINDOW_DAYS + 1))  # fenêtre précédente, sans recouvrement
    lifts = [{"id": k, "label": labels.get(k, k), "e1rm": current[k]["e1rm"], "reference": earlier[k]["e1rm"], "score": _pct(current[k]["e1rm"], earlier[k]["e1rm"])}
             for k in sorted(current) if k in earlier]
    if len(lifts) < STRENGTH_MIN_LIFTS:
        return None
    return {"score": round(sum(x["score"] for x in lifts) / len(lifts)), "lifts": lifts}


def strength_axis(sessions: list[dict[str, Any]], today: date, labels: dict[str, str]) -> dict[str, Any]:
    now = _strength_at(sessions, today, labels)
    before = _strength_at(sessions, today - timedelta(weeks=COMPARE_WEEKS), labels)
    return {"id": "strength", "status": "ok" if now else "insufficient", "reason": None if now else "few_lifts", "now": now, "before": before, "delta": _delta(now, before)}


# ---------- assemblage (ST14, ST20) ----------

def radar_view(sessions: list[dict[str, Any]], activities: list[dict[str, Any]], facts: dict[str, Any], goals: list[dict[str, Any]], labels: dict[str, str],
               regularity_on: bool, today: date) -> dict[str, Any]:
    weeks = progress.weekly_volume(sessions, activities, today, weeks=VOLUME_REF_WEEKS + VOLUME_WEEKS + COMPARE_WEEKS + 1)
    target = T.pick_target(goals, today)
    km_target = T.volume_target_km(target["time_min"], target["distance_km"]) if target else None
    axes = [volume_axis(weeks, km_target), regularity_axis(sessions, today, regularity_on), endurance_axis(activities, facts, goals, today), strength_axis(sessions, today, labels)]
    drawn = [a for a in axes if a["status"] == "ok"]
    chart = len(drawn) >= MIN_AXES
    # la comparaison n'est tracée que si chaque axe dessiné a une valeur d'il y a 4 semaines : sinon la forme changerait d'axes d'un polygone à l'autre
    compare = chart and all(a["before"] for a in drawn)
    return {"today": today.isoformat(), "compare_weeks": COMPARE_WEEKS, "axes": axes, "chart": chart, "compare": compare, "not_measured": list(NOT_MEASURED)}
