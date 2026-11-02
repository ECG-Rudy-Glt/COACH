"""Bilan de forme du jour (R1, R2, R4) : trois réponses en deux touches, une proposition d'allègement validée par l'utilisateur. Déterministe, sans LLM.

Les mesures subjectives suivent bien la charge d'entraînement (Saw et al. 2016, RUN-014 / REC-001), mais aucune étude lue ne fixe de seuil :
les seuils ci-dessous sont une convention de pratique. Le bilan ne peut qu'alléger (R4), ne pose aucun diagnostic et renvoie vers un professionnel en cas de douleur.
HRV et FC de repos de la montre ne sont pas utilisées : rien dans les publications relues ne justifie un seuil décisif (R5).
"""
from datetime import date, timedelta
from typing import Any

METRICS = ("checkin_energy", "checkin_sleep", "checkin_soreness", "checkin_pain")  # stockées dans garmin_metrics, une ligne par jour et par mesure
FACTOR = 0.7  # R1 : volume −30 %
MIN_SESSION = 15
POOR_ENERGY, POOR_SLEEP, POOR_SORENESS = 2, 2, 4  # énergie et sommeil de 1 (très mauvais) à 5 ; courbatures de 1 (aucune) à 5 (très fortes)
DEGRADED_SIGNALS = 2  # au moins deux signaux faibles sur trois
WEEK_DAYS, WEEK_DEGRADED = 7, 3  # R2 : 3 jours dégradés sur 7
APPLIED_NOTE = "Allégée d'après votre bilan du jour"  # une séance déjà allégée par le bilan du jour ne l'est pas une seconde fois
PAIN_NOTE = "Une douleur localisée n'est pas un manque de forme : si elle persiste ou augmente, consultez un professionnel de santé (S1, S2)."


def is_degraded(energy: int, sleep: int, soreness: int) -> bool:
    poor = (energy <= POOR_ENERGY) + (sleep <= POOR_SLEEP) + (soreness >= POOR_SORENESS)
    return poor >= DEGRADED_SIGNALS


def rows(day: date, energy: int, sleep: int, soreness: int, pain: bool) -> list[dict[str, Any]]:
    return [{"day": day, "metric": m, "value": float(v)} for m, v in zip(METRICS, (energy, sleep, soreness, int(pain)), strict=True)]


def state_on(metrics: list[dict[str, Any]], day: date) -> dict[str, Any] | None:
    got = {m["metric"]: m["value"] for m in metrics if m["day"] == day}
    if not all(k in got for k in METRICS[:3]):
        return None
    e, s, c = (int(got[k]) for k in METRICS[:3])
    return {"day": day.isoformat(), "energy": e, "sleep": s, "soreness": c, "pain": bool(got.get("checkin_pain")), "degraded": is_degraded(e, s, c)}


def week_alert(metrics: list[dict[str, Any]], today: date) -> bool:
    """R2 : le bilan est dégradé 3 jours sur les 7 derniers (aujourd'hui compris)."""
    days = [today - timedelta(days=i) for i in range(WEEK_DAYS)]
    return sum(1 for d in days if (st := state_on(metrics, d)) and st["degraded"]) >= WEEK_DEGRADED


def proposals(state: dict[str, Any] | None, sessions_today: list[dict[str, Any]]) -> list[dict[str, Any]]:
    """R1, R4 : séance de qualité → footing facile, sinon durée × 0,7 ; jamais d'augmentation. Aucune proposition si le bilan n'est pas dégradé."""
    if not state or not state["degraded"]:
        return []
    out = []
    for s in sessions_today:
        if s["status"] != "planned" or any(n.startswith(APPLIED_NOTE) for n in s.get("notes") or []):
            continue
        if s["kind"] == "run_quality":
            out.append({"session_id": s["id"], "title": s["title"], "action": "swap_easy", "rules": ["R1", "R4"]})
        else:
            new = max(MIN_SESSION, round(s["duration_min"] * FACTOR))
            if new < s["duration_min"]:
                out.append({"session_id": s["id"], "title": s["title"], "action": "reduce", "duration_from": s["duration_min"], "duration_to": new, "rules": ["R1", "R4"]})
    return out
