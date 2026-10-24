"""Règles météo W1 à W6 (docs/rules.md) : statut d'une séance en extérieur d'après la prévision de son créneau. Déterministe, pur, sans réseau.

Seuils prudents et documentés ; ce n'est jamais un avis médical, et rien ne change le plan sans l'accord de l'utilisateur."""
import math
from typing import Any

OUTDOOR = {"run_easy", "run_long", "run_quality", "sport_bike", "sport_walk"}
DEFAULT_HOUR = 18

STORM_CODES = {95, 96, 99}  # codes WMO : orage, orage avec grêle
FREEZING_CODES = {56, 57, 66, 67}  # bruine / pluie verglaçante
GUST_WATCH_KMH = 41  # W2 : force 6 de Beaufort (22 nœuds)
GUST_AVOID_KMH = 52  # W2 : force 7 de Beaufort (28 nœuds)
RAIN_WATCH_PROB = 60  # W3 : probabilité (%) et cumul (mm) pour « à surveiller »
RAIN_WATCH_MM = 2.0
RAIN_AVOID_MM_H = 4.0  # W3 : pluie forte, au moins 4 mm en une heure
HEAT_WATCH_C = 32  # W4 : 90 °F, « extrême prudence » du NWS
HEAT_AVOID_C = 39  # W4 : 103 °F, « danger » du NWS
COLD_WATCH_C = -10  # W5
COLD_AVOID_C = -28  # W5 : −19 °F, peau exposée gelée en 30 min selon le NWS
ICE_TEMP_C = 1  # W6
STATUS_ORDER = {"ok": 0, "watch": 1, "avoid": 2}

# repli quand aucune règle météo n'est déclenchée dans la fenêtre : pas de texte
ADAPT = {
    "W1": "Orage : reportez la séance, ou faites-la en salle ou sur tapis. Ne restez pas dehors quand il gronde.",
    "W2": "Vent fort : choisissez un parcours abrité, raccourcissez, ou passez en salle ou sur home-trainer.",
    "W3": "Pluie : tenue imperméable et parcours sûr, ou déplacez la séance sur un jour plus sec.",
    "W4": "Chaleur : sortez plus tôt le matin ou tard le soir, réduisez l'allure, buvez régulièrement, ou passez en salle.",
    "W5": "Grand froid : couvrez les extrémités et le visage, raccourcissez, ou passez en salle.",
    "W6": "Verglas possible : évitez la course et le vélo sur les surfaces gelées, préférez la salle, le tapis ou une marche prudente.",
}


def window(hour: int, duration_min: int) -> list[int]:
    """Heures locales couvertes par la séance (au moins une, jusqu'à 23 h)."""
    h0 = min(max(int(hour), 0), 23)
    return list(range(h0, min(24, h0 + max(1, math.ceil(duration_min / 60)))))


def _vals(rows: list[dict[str, Any]], key: str) -> list[float]:
    return [r[key] for r in rows if r.get(key) is not None]


def assess(day_hours: dict[int, dict[str, Any]], hour: int, duration_min: int) -> dict[str, Any] | None:
    """Statut météo d'une séance : {"status": ok|watch|avoid, "reasons": [...], "forecast": {...}}, ou None si la prévision du créneau manque."""
    hours = window(hour, duration_min)
    rows = [day_hours[h] for h in hours if h in day_hours]
    if not rows:
        return None
    gust = max(_vals(rows, "gust"), default=None)
    feels_lo, feels_hi = min(_vals(rows, "feels"), default=None), max(_vals(rows, "feels"), default=None)
    temp_lo = min(_vals(rows, "t"), default=None)
    mm = sum(_vals(rows, "mm"))
    mm_h = max(_vals(rows, "mm"), default=0.0)
    prob = max(_vals(rows, "pp"), default=0.0)
    codes = {int(c) for c in _vals(rows, "code")}
    around = [day_hours[h] for h in range(max(0, hours[0] - 2), min(24, hours[-1] + 3)) if h in day_hours]  # un orage juste avant ou après le créneau compte
    before = [day_hours[h] for h in range(max(0, hours[0] - 6), hours[0]) if h in day_hours]
    reasons: list[dict[str, Any]] = []

    def add(rule: str, level: str, text: str) -> None:
        reasons.append({"rule": rule, "level": level, "text": text, "adapt": ADAPT[rule]})

    if codes & STORM_CODES:  # W1
        add("W1", "avoid", "Orage prévu pendant la séance.")
    elif {int(c) for c in _vals(around, "code")} & STORM_CODES:
        add("W1", "watch", "Orage prévu juste avant ou après la séance : le créneau peut changer.")
    if gust is not None and gust >= GUST_AVOID_KMH:  # W2
        add("W2", "avoid", f"Rafales prévues jusqu'à {round(gust)} km/h (vent de force 7 ou plus).")
    elif gust is not None and gust >= GUST_WATCH_KMH:
        add("W2", "watch", f"Rafales prévues jusqu'à {round(gust)} km/h (vent de force 6).")
    if mm_h >= RAIN_AVOID_MM_H:  # W3
        add("W3", "avoid", f"Pluie forte prévue : jusqu'à {round(mm_h, 1)} mm en une heure.")
    elif prob >= RAIN_WATCH_PROB and mm >= RAIN_WATCH_MM:
        add("W3", "watch", f"Pluie probable ({round(prob)} %, environ {round(mm, 1)} mm sur la séance).")
    if feels_hi is not None and feels_hi >= HEAT_AVOID_C:  # W4
        add("W4", "avoid", f"Chaleur : température ressentie jusqu'à {round(feels_hi)} °C.")
    elif feels_hi is not None and feels_hi >= HEAT_WATCH_C:
        add("W4", "watch", f"Forte chaleur : température ressentie jusqu'à {round(feels_hi)} °C.")
    if feels_lo is not None and feels_lo <= COLD_AVOID_C:  # W5
        add("W5", "avoid", f"Grand froid : température ressentie jusqu'à {round(feels_lo)} °C.")
    elif feels_lo is not None and feels_lo <= COLD_WATCH_C:
        add("W5", "watch", f"Froid vif : température ressentie jusqu'à {round(feels_lo)} °C.")
    wet_now = mm >= 0.1 or bool(codes & FREEZING_CODES)  # W6
    wet_before = sum(_vals(before, "mm")) >= 0.5
    if temp_lo is not None and temp_lo <= ICE_TEMP_C and (wet_now or codes & FREEZING_CODES):
        add("W6", "avoid", f"Risque de verglas : {round(temp_lo)} °C avec des précipitations.")
    elif temp_lo is not None and temp_lo <= ICE_TEMP_C and wet_before:
        add("W6", "watch", f"Verglas possible : {round(temp_lo)} °C après des précipitations dans les heures précédentes.")
    status = max((r["level"] for r in reasons), key=STATUS_ORDER.__getitem__, default="ok")
    return {"status": status, "reasons": reasons,
            "forecast": {"hour": hours[0], "temp_c": None if temp_lo is None else round(temp_lo), "feels_c": None if feels_hi is None else round(feels_hi),
                         "feels_min_c": None if feels_lo is None else round(feels_lo), "gust_kmh": None if gust is None else round(gust),
                         "rain_mm": round(mm, 1), "rain_prob": round(prob), "storm": bool(codes & STORM_CODES)}}
