"""Cibles nutritionnelles et suivi du poids, déterministes (docs/rules.md N1 à N8). Le LLM ne calcule aucun chiffre."""
from __future__ import annotations

from dataclasses import dataclass, field
from datetime import date, timedelta
from typing import Any

KCAL_PER_KG = 7700  # repère classique, valable à court terme (voir docs/references.md)
PAL = {"sédentaire": 1.25, "mixte": 1.40, "physique": 1.60}  # activité quotidienne hors séances
MET = {"run": 8.0, "bike": 7.0, "strength": 4.0, "swim": 6.0, "walk": 3.5, "other": 4.0, "hybrid": 6.0}  # hybride (CrossFit, Hyrox) : valeur moyenne entre aérobie (≈ 6) et metcons (≈ 8+)
KIND_SPORT = {"run_easy": "run", "run_long": "run", "run_quality": "run", "strength_upper": "strength", "strength_lower": "strength",
              "strength_full": "strength", "strength_crossfit": "hybrid", "sport_bike": "bike", "sport_swim": "swim", "sport_walk": "walk", "sport_other": "other"}
MIN_KCAL = {"homme": 1500, "femme": 1200}


@dataclass
class NutritionProfile:
    sex: str = "homme"
    age: int = 30
    height_cm: float = 170
    weight_kg: float = 70
    work: str = "sédentaire"
    direction: str = "perdre"  # perdre | maintenir | prendre
    target_kg: float | None = None
    weeks_to_event: int | None = None
    blocked_reason: str | None = None  # S4/S6 : pas de déficit
    exercise_kcal_day: float = 0.0
    notes: list[str] = field(default_factory=list)


def bmr_mifflin(sex: str, kg: float, cm: float, age: int) -> float:
    return 10 * kg + 6.25 * cm - 5 * age + (5 if sex != "femme" else -161)


def build_profile(facts: dict[str, Any], today: date, latest_kg: float | None, sessions: list[dict[str, Any]],
                  weeks_to_event: int | None) -> NutritionProfile:
    p = NutritionProfile()
    p.sex = "femme" if facts.get("body.sex_for_calc") == "femme" else "homme"
    by = facts.get("body.birth_year")
    p.age = today.year - int(by) if isinstance(by, int | float) and by else 30
    p.height_cm = float(facts.get("body.height_cm") or 170)
    p.weight_kg = float(latest_kg or facts.get("body.weight_kg") or 70)
    p.work = facts.get("constraints.work_activity") or "sédentaire"
    d = facts.get("goal.weight_direction")
    p.direction = {"perdre": "perdre", "prendre": "prendre"}.get(d, "maintenir")
    t = facts.get("goal.target_weight_kg")
    p.target_kg = float(t) if isinstance(t, int | float) and t else None
    p.weeks_to_event = weeks_to_event
    cond = set(facts.get("health.conditions") or [])
    if p.age < 18:
        p.blocked_reason = "Mineur : pas de plan de perte de poids (règle N7). Parlez-en à un professionnel de santé."
    elif cond & {"grossesse ou post-partum", "trouble alimentaire passé"}:
        p.blocked_reason = "Situation déclarée : pas de déficit calorique proposé (règle N7). Un professionnel de santé est le bon interlocuteur."
    # dépense des séances : (MET − 1) × poids × heures, moyenne quotidienne sur les séances planifiées de la semaine
    kcal = 0.0
    for s in sessions:
        sport = KIND_SPORT.get(s["kind"], "other")
        kcal += (MET[sport] - 1) * p.weight_kg * s["duration_min"] / 60
    p.exercise_kcal_day = round(kcal / 7, 0)
    return p


def targets(p: NutritionProfile, day_load: str = "mean") -> dict[str, Any]:
    """Cibles du jour. `day_load` : training | rest | mean (±120 kcal de glucides selon la charge, moyenne inchangée)."""
    bmr = bmr_mifflin(p.sex, p.weight_kg, p.height_cm, p.age)
    tdee = bmr * PAL.get(p.work, 1.25) + p.exercise_kcal_day
    rate = 0.0
    if p.direction == "perdre" and not p.blocked_reason:
        rate = 0.005 if (p.weeks_to_event is not None and p.weeks_to_event <= 12) else 0.0075  # N4 : 0,5 % près d'un objectif, 0,75 % sinon
    elif p.direction == "prendre" and not p.blocked_reason:
        rate = -0.0025
    deficit = rate * p.weight_kg * KCAL_PER_KG / 7
    floor = max(bmr, MIN_KCAL[p.sex])  # N1 : jamais sous le métabolisme de base
    kcal = max(tdee - deficit, floor)
    limited = kcal > tdee - deficit + 1
    shift = {"training": 120, "rest": -120}.get(day_load, 0)
    kcal_day = max(kcal + shift, floor)  # le plancher de sécurité s'applique aussi aux jours de repos (N1)
    protein = round(p.weight_kg * (2.0 if p.direction == "perdre" else 1.8))  # N2 : 1,8 à 2,4 g/kg ; 2,0 en déficit avec musculation
    fat = round(p.weight_kg * 0.8)  # N3
    carbs = max(round((kcal_day - protein * 4 - fat * 9) / 4), 0)
    rounded = -(-kcal_day // 10) * 10 if (limited or kcal_day <= floor + 1) else round(kcal_day / 10) * 10  # plancher appliqué : on arrondit vers le haut, jamais sous le BMR
    out = {"kcal": int(rounded), "protein_g": protein, "carbs_g": carbs, "fat_g": fat, "fiber_g": 28, "bmr": round(bmr),
           "tdee": round(tdee), "deficit_kcal": round(max(tdee - kcal, 0)), "rate_pct_per_week": round(rate * 100, 2), "floor_applied": limited,
           "day_load": day_load, "rules": ["N1", "N2", "N3"]}
    if p.blocked_reason:
        out["notice"] = p.blocked_reason
    elif limited:
        out["notice"] = "Le déficit est limité par le plancher de sécurité (règle N1) : l'objectif sera atteint plus lentement."
    return out


def trend(entries: list[dict[str, Any]], today: date) -> dict[str, Any]:
    """Tendance de poids : moyenne glissante de 7 jours (N5) et rythme hebdomadaire sur 21 jours."""
    pts = sorted(((e["day"], float(e["kg"])) for e in entries), key=lambda x: x[0])
    if not pts:
        return {"series": [], "current": None, "rate_pct_per_week": None}
    series = []
    for i, (d, _) in enumerate(pts):
        win = [kg for dd, kg in pts[: i + 1] if (d - dd).days < 7]
        series.append({"day": d.isoformat(), "kg": round(pts[i][1], 1), "avg": round(sum(win) / len(win), 2)})
    cur = series[-1]["avg"]
    recent = [s for s in series if (today - date.fromisoformat(s["day"])).days <= 21]
    rate = None
    if len(recent) >= 3 and (date.fromisoformat(recent[-1]["day"]) - date.fromisoformat(recent[0]["day"])).days >= 7:
        days = (date.fromisoformat(recent[-1]["day"]) - date.fromisoformat(recent[0]["day"])).days
        rate = round((recent[-1]["avg"] - recent[0]["avg"]) / days * 7 / recent[0]["avg"] * 100, 2)
    return {"series": series[-90:], "current": cur, "first": series[0]["avg"], "rate_pct_per_week": rate}


PERIOD_DAYS = {1: 30, 3: 91, 6: 182, 12: 365}  # périodes proposées (mois) → jours
DAYS_PER_MONTH = 30.44
MIN_TREND_WEIGHINGS, TREND_RECENT_DAYS = 3, 14  # N5 : au moins 3 pesées sur 14 jours pour afficher une tendance


def _regression(pts: list[tuple[int, float]]) -> tuple[float, float] | None:
    """Droite des moindres carrés (jours, kg) : (pente en kg par jour, valeur ajustée au dernier jour), ou None si les jours sont identiques."""
    n = len(pts)
    mx, my = sum(x for x, _ in pts) / n, sum(y for _, y in pts) / n
    sxx = sum((x - mx) ** 2 for x, _ in pts)
    if sxx == 0:
        return None
    slope = sum((x - mx) * (y - my) for x, y in pts) / sxx
    return slope, my + slope * (pts[-1][0] - mx)


def weight_trend(entries: list[dict[str, Any]], today: date, months: int = 3, target_kg: float | None = None) -> dict[str, Any]:
    """Tendance de poids sur plusieurs mois (N5) : courbe lissée (moyenne de 7 jours, interne), pente par régression linéaire des pesées de la période
    en kg et % par mois, écart à l'objectif et date estimée d'atteinte. Aucune tendance sans 3 pesées sur les 14 derniers jours."""
    months = months if months in PERIOD_DAYS else 3
    since = today - timedelta(days=PERIOD_DAYS[months])
    pts = sorted(((e["day"], float(e["kg"])) for e in entries), key=lambda x: x[0])
    smooth = [{"day": d.isoformat(), "kg": round(kg, 1), "avg": round(sum(k for dd, k in pts[: i + 1] if (d - dd).days < 7) / sum(1 for dd, _ in pts[: i + 1] if (d - dd).days < 7), 2)}
              for i, (d, kg) in enumerate(pts)]
    series = [x for x in smooth if date.fromisoformat(x["day"]) >= since]
    out: dict[str, Any] = {"months": months, "series": series, "current": smooth[-1]["avg"] if smooth else None, "target_kg": target_kg,
                           "kg_per_month": None, "pct_per_month": None, "remaining_kg": None, "eta_date": None, "reason": None}
    if not series:
        out["reason"] = "none"
        return out
    recent = sum(1 for x in series if (today - date.fromisoformat(x["day"])).days < TREND_RECENT_DAYS)
    fit = _regression([((date.fromisoformat(x["day"]) - since).days, x["kg"]) for x in series]) if recent >= MIN_TREND_WEIGHINGS else None
    if fit is None:
        out["reason"] = "few"
    else:
        slope, end = fit
        out["kg_per_month"] = round(slope * DAYS_PER_MONTH, 2)
        out["pct_per_month"] = round(slope * DAYS_PER_MONTH / end * 100, 2)
        if target_kg:
            out["remaining_kg"] = round(out["current"] - target_kg, 1)
            days = (target_kg - end) / slope if slope else None
            if days is not None and 0 < days <= 3 * 365:
                out["eta_date"] = (today + timedelta(days=round(days))).isoformat()
    if target_kg and out["remaining_kg"] is None:
        out["remaining_kg"] = round(out["current"] - target_kg, 1)
    return out


def advice(p: NutritionProfile, tg: dict[str, Any], tr: dict[str, Any], adherence_days: int) -> list[str]:
    """Conseils d'ajustement (N4, N5) : jamais de baisse sous le plancher, jamais d'alarmisme sur un seul chiffre."""
    out = []
    rate = tr.get("rate_pct_per_week")
    if p.direction == "perdre" and not p.blocked_reason:
        if rate is None:
            out.append("Pesez-vous au moins deux fois par semaine, le matin : la tendance sur plusieurs semaines compte, pas le chiffre d'un jour (N5).")
        elif adherence_days >= 14 and rate > -0.25:
            out.append(f"Votre poids baisse d'environ {abs(rate):.2f} % par semaine, sous l'objectif ({tg['rate_pct_per_week']} %). "
                       "Vérifiez d'abord que vos repas sont bien tous renseignés ; sinon une baisse de 100 à 150 kcal par jour est raisonnable (N4).")
        elif rate < -1.0:
            out.append(f"Vous perdez environ {abs(rate):.2f} % par semaine : c'est rapide pour conserver le muscle. Ajoutez 150 kcal par jour (N4).")
        else:
            out.append("Le rythme de perte est dans la zone visée : continuez ainsi.")
    if p.target_kg and tr.get("current") and p.direction == "perdre" and tg["rate_pct_per_week"]:
        weeks = (tr["current"] - p.target_kg) / (tg["rate_pct_per_week"] / 100 * tr["current"])
        if weeks > 0:
            out.append(f"À ce rythme, {p.target_kg:g} kg seraient atteints dans environ {round(weeks)} semaines (estimation).")
    return out
