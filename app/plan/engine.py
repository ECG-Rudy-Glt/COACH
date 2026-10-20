"""Moteur de plan déterministe (règles : docs/rules.md). Aucun appel externe, aucune aléa."""
from __future__ import annotations

import re
from dataclasses import dataclass, field
from datetime import date, timedelta
from typing import Any

from app.plan import crossfit as CF
from app.plan import strength as S
from app.plan import trajectory as T
from app.plan.cycles import Cycle, cycle_for

DAYS = ["lundi", "mardi", "mercredi", "jeudi", "vendredi", "samedi", "dimanche"]
DEFAULT_EASY_PACE = 6.5  # min/km si aucune donnée
GROWTH_STEP = 1.08  # G1 : montée ≤ 10 % par semaine
RETURN_GROWTH_MAX = 1.15  # G3 : reprise après arrêt, retour au niveau habituel en 4 à 6 semaines
DELOAD_FACTOR = 0.65  # G2 : semaine allégée (−35 %)
KEY = {"run_long", "run_quality", "strength_lower"}
RUN_ZONES = {"genou", "cheville", "hanche", "tibia", "tendon d'Achille", "mollet", "pied", "ischio-jambiers"}  # S2 : zones qui portent la course


@dataclass
class Profile:
    runs: bool = False
    strength: bool = False
    crossfit: bool = False  # sport déclaré : une séance de conditionnement par semaine (M9)
    trail: bool = False
    days_per_week: int = 3
    blocked: set[int] = field(default_factory=set)
    run_days: set[int] = field(default_factory=set)
    strength_days: set[int] = field(default_factory=set)
    weekday_max: int = 60
    weekend_max: int = 120
    weekly_km: float = 0.0  # volume mesuré ou déclaré sur 8 semaines
    usual_km: float = 0.0  # volume habituel mesuré sur 12 mois (historique Garmin)
    weeks_since_run: int | None = None
    longest_min: float = 0.0  # plus longue sortie de course récente (minutes) : point de départ de la sortie longue d'un objectif
    easy_pace: float = DEFAULT_EASY_PACE
    hr_max: int | None = None
    strength_per_week: int = 2
    level: str = "débutant"
    focus_upper: bool = False
    cutting: bool = False
    age: int | None = None
    weekly_vert: float = 0.0
    after_break: bool = False
    injuries: set[str] = field(default_factory=set)
    red_flags: bool = False
    run_injury: bool = False  # blessure active sur une zone qui porte la course : volume et intensité gelés (S2)
    event: dict[str, Any] | None = None  # {"date": date, "title": str, "distance_km": float, "elevation_m": float}
    deload_cycle: int = 4  # 3+1 par défaut (2+1 : 3)
    facts: dict[str, Any] = field(default_factory=dict)
    today: date = field(default_factory=date.today)
    target: dict[str, Any] | None = None  # objectif de performance daté (trajectoire, C11) : {"date", "title", "distance_km", "time_min"}
    level_min: float | None = None  # temps équivalent actuel sur la distance de l'objectif (C10)
    target_volume_min: float | None = None  # plafond de volume hebdomadaire de course (minutes) tant que l'objectif est lointain (C12)


def _days(v: Any) -> set[int]:
    return {DAYS.index(d) for d in (v or []) if d in DAYS}


def _num(v: Any, default: float = 0.0) -> float:
    return float(v) if isinstance(v, int | float) and not isinstance(v, bool) else default


def build_profile(facts: dict[str, Any], goals: list[dict[str, Any]], today: date) -> Profile:
    sports = set(facts.get("sports.practiced") or [])
    p = Profile(facts=facts, today=today)
    p.runs = bool(sports & {"running", "trail"})
    p.trail = "trail" in sports
    p.strength = "strength" in sports
    p.crossfit = bool(sports & {"crossfit", "hyrox"})
    p.days_per_week = max(2, min(6, int(_num(facts.get("constraints.training_days"), 3))))
    p.blocked = _days(facts.get("multisport.blocked_days"))
    p.run_days = _days(facts.get("multisport.preferred_run_days"))
    p.strength_days = _days(facts.get("multisport.preferred_strength_days"))
    p.weekday_max = int(_num(facts.get("constraints.weekday_session_max_min"), 60)) or 60
    p.weekend_max = int(_num(facts.get("constraints.weekend_session_max_min"), 0)) or max(p.weekday_max, 120)
    p.weekly_km = _num(facts.get("running.weekly_km_8w"))
    p.usual_km = _num(facts.get("running.weekly_km_12m"))
    ws = facts.get("running.weeks_since_last_run")
    p.weeks_since_run = int(ws) if isinstance(ws, int | float) and not isinstance(ws, bool) else None
    p.longest_min = _num(facts.get("running.longest_recent_min"))
    best10 = _num(facts.get("running.best_10k_min"))
    if best10 > 0:
        p.easy_pace = round(best10 / 10 * 1.25, 2)  # allure facile ≈ allure 10 km × 1,25
    hr = _num(facts.get("running.hr_max"))
    p.hr_max = int(hr) if hr >= 140 else None
    declared = round(_num(facts.get("strength.sessions_per_week"), 2)) or 2
    measured = round(_num(facts.get("strength.sessions_per_week_12m")))  # fréquence réelle (Garmin) : le plan ne descend pas en dessous
    p.strength_per_week = max(1, min(4, max(declared, measured)))
    p.level = facts.get("strength.level") or "débutant"
    focus = set(facts.get("goal.physique_focus") or [])
    p.focus_upper = bool(focus & {"haut du corps", "épaules", "dos", "pectoraux", "bras"})
    p.cutting = facts.get("goal.weight_direction") == "perdre"
    by = _num(facts.get("body.birth_year"))
    p.age = today.year - int(by) if by else None
    p.weekly_vert = _num(facts.get("trail.weekly_vert_m"))
    p.after_break = facts.get("history.recent_break") in ("oui blessure", "oui autre raison")
    p.injuries = set(facts.get("history.injuries") or []) - {"aucune"}
    p.run_injury = bool(p.injuries & RUN_ZONES)
    flags = set(facts.get("health.red_flags") or []) - {"aucun"}
    p.red_flags = bool(flags) and facts.get("health.red_flags_discussed") != "oui"
    if (p.age and p.age > 45) or p.after_break:
        p.deload_cycle = 3  # G2 : 2+1
    events = [g for g in goals if g["status"] == "active" and g["kind"] == "event" and g.get("target_date") and g["target_date"] >= today]
    if events:
        events.sort(key=lambda g: ({"principal": 0, "important": 1}.get(g["priority"], 2), g["target_date"]))
        e = events[0]
        d = e.get("details") or {}
        dist = _num(d.get("distance_km"))
        if not dist:  # « Trail 50 km » : distance déduite du titre quand elle n'est pas renseignée
            m = re.search(r"(\d+(?:[.,]\d+)?)\s*km", e["title"], re.I)
            dist = float(m.group(1).replace(",", ".")) if m else 0.0
        p.event = {"date": e["target_date"], "title": e["title"], "distance_km": dist, "elevation_m": _num(d.get("elevation_m"))}
    p.target = T.pick_target(goals, today)
    if p.target:
        level = T.current_level(facts, p.target["distance_km"])
        p.level_min = level[0] if level else None
        p.target_volume_min = T.volume_target_km(p.target["time_min"], p.target["distance_km"]) * p.easy_pace
    return p


@dataclass
class Session:
    date: date
    kind: str  # run_easy | run_long | run_quality | strength_upper | strength_lower | strength_full | strength_crossfit
    title: str
    duration_min: int
    details: dict[str, Any] = field(default_factory=dict)
    rules: list[str] = field(default_factory=list)
    notes: list[str] = field(default_factory=list)


def _monday(d: date) -> date:
    return d - timedelta(days=d.weekday())


def zone_text(p: Profile, level: str) -> str:
    """Zones : FC max si connue, sinon allure ; les deux si disponibles (décision 4)."""
    pace = p.easy_pace
    parts = []
    if p.hr_max:
        lo, hi = (0.60, 0.75) if level == "easy" else (0.85, 0.92)
        parts.append(f"{round(p.hr_max * lo)}-{round(p.hr_max * hi)} bpm")
    q = pace if level == "easy" else pace / 1.25 * 1.04
    parts.append(f"allure ≈ {int(q)}:{round(q % 1 * 60):02d}/km")
    return ", ".join(parts)


def weekly_volumes(p: Profile, weeks: int, weeks_to_event: int | None, offset: int = 0, ceiling: float | None = None) -> list[tuple[float, bool, bool]]:
    """Volume de course en minutes par semaine : (minutes, décharge, affûtage). G1, G2, G3, C6.

    Le point de départ s'appuie sur l'historique : après un arrêt, on repart à 50 % (≤ 4 semaines d'arrêt) ou 30 % du volume habituel,
    puis on remonte en 4 à 6 semaines jusqu'à ce volume (G3), et ensuite de 8 % par semaine au plus (G1).
    `offset` : rang de la première semaine dans le bloc en cours (le cycle 3+1 continue d'une génération à l'autre, G7).
    `ceiling` : plafond de volume visé par la trajectoire (C12) ; sans lui, le volume monterait sans limite tant qu'aucun événement n'est proche.
    """
    pace = p.easy_pace
    measured = p.weekly_km * pace
    usual = max(p.usual_km * pace, measured)
    if usual <= 0:
        measured = usual = 12 * pace  # aucune donnée : 12 km par semaine par défaut
    if measured >= 0.6 * usual:
        start = measured
    else:
        frac = 0.5 if (p.weeks_since_run is not None and p.weeks_since_run <= 4) else 0.3
        start = max(measured, frac * usual, 75 if usual >= 150 else 45)
    if p.after_break and measured >= 0.6 * usual:
        start *= 0.5  # arrêt déclaré sans historique mesuré
    cap = p.weekday_max * (p.days_per_week - 1) + p.weekend_max
    cap_run = min(cap, 600, ceiling) if ceiling else min(cap, 600)
    out: list[tuple[float, bool, bool]] = []
    last_build = start
    for i in range(weeks):
        taper = weeks_to_event is not None and 0 <= weeks_to_event - i <= 1
        deload = p.deload_cycle - 1 == (i + offset) % p.deload_cycle and not taper
        if i == 0:
            last_build = min(start, cap_run)
            v = last_build * DELOAD_FACTOR if deload else last_build
        elif deload:
            v = last_build * DELOAD_FACTOR
        elif p.run_injury:  # S2 : progression gelée tant que la douleur est déclarée
            v = last_build
        elif taper:
            v = last_build * 0.6
        else:
            g = min(RETURN_GROWTH_MAX, (usual / max(start, 1)) ** (1 / 5)) if last_build < usual else GROWTH_STEP
            v = min(last_build * max(g, GROWTH_STEP), cap_run)
            last_build = v
        out.append((round(v), deload, taper))
    return out


LONG_STEP_MIN = 10  # C9 : la sortie longue gagne 10 minutes par semaine depuis la dernière sortie réellement faite
LONG_PEAK_SHARE = 0.75  # C9 : sortie la plus longue ≈ 75 % de la durée estimée de l'objectif, au plus 2 h 30


def event_minutes(p: Profile) -> float:
    """Durée estimée de l'objectif, à allure facile : distance + 6 min par 100 m de dénivelé."""
    e = p.event or {}
    return float(e.get("distance_km") or 0) * p.easy_pace + float(e.get("elevation_m") or 0) / 100 * 6


def event_long_peak(p: Profile) -> int:
    return min(round(LONG_PEAK_SHARE * event_minutes(p) / 5) * 5, 150)


def event_long_run(p: Profile, weeks_to_event: int | None, k: int) -> int | None:
    """Durée (min) de la sortie longue guidée par l'objectif, dans les 12 semaines qui le précèdent (C9) ; None hors de cette fenêtre.

    `k` : rang de la semaine dans la génération en cours. Le point de départ est la plus longue sortie récente mesurée par la montre :
    si la sortie n'a pas été faite, la progression ne s'emballe pas à la génération suivante.
    """
    if not p.event or not p.runs or p.event["distance_km"] <= 0 or weeks_to_event is None or not 0 < weeks_to_event <= 12:
        return None
    peak = event_long_peak(p)
    if weeks_to_event == 1:  # affûtage
        return max(round(peak * 0.55 / 5) * 5, 30)
    start = max(p.longest_min, 30.0)
    return int(min(peak, round((start + LONG_STEP_MIN * (k + 1)) / 5) * 5))


def outlook(p: Profile, today: date) -> dict[str, Any] | None:
    """Projection du volume jusqu'à l'événement : l'objectif est-il atteignable avec la montée prudente du plan ?"""
    if not p.event or p.event["distance_km"] <= 0 or not p.runs:
        return None
    weeks_to_event = max(0, (p.event["date"] - _monday(today)).days // 7)
    vols = weekly_volumes(p, min(weeks_to_event + 1, 60), weeks_to_event)
    peak_min = max((v for v, _, taper in vols if not taper), default=0)
    guided = 0
    if 0 < weeks_to_event <= 12:  # C9 : la sortie longue guidée par l'objectif porte le volume (long + 2 footings de 25 min)
        guided = min(event_long_peak(p), max(p.longest_min, 30) + LONG_STEP_MIN * max(weeks_to_event - 1, 0)) + 50
        peak_min = max(peak_min, guided)
    peak_km = round(peak_min / p.easy_pace)
    dist = p.event["distance_km"]
    needed = round(dist if dist < 30 else 0.7 * dist)  # repère de pratique (C8), pas une loi
    ok = peak_km >= needed
    how = (f"Avec la sortie longue qui monte de 10 minutes par semaine (jusqu'à environ {event_long_peak(p)} min), "
           f"le volume atteindrait environ {peak_km} km par semaine avant l'affûtage. ") if guided else \
        f"Avec la montée prudente du plan, le volume atteindrait environ {peak_km} km par semaine avant l'affûtage. "
    msg = (how
           + ("C'est cohérent avec l'objectif." if ok else
              f"Pour {int(dist)} km, une préparation raisonnable se situe plutôt autour de {needed} km par semaine : "
              "envisagez de repousser l'échéance ou de viser une distance plus courte."))
    return {"weeks_to_event": weeks_to_event, "projected_peak_km": peak_km, "needed_peak_km": needed, "ok": ok, "message": msg,
            "event": p.event["title"]}


def advice(p: Profile) -> list[str]:
    """Conseils d'organisation (non bloquants) affichés avec le plan."""
    out = []
    if p.strength and p.focus_upper and p.strength_per_week < 3:
        out.append("Pour développer le haut du corps, 3 séances de musculation par semaine permettent de le travailler deux fois, "
                   "avec les jambes en entretien. Vous pouvez passer à 3 dans vos réponses (Musculation, fréquence).")
    if p.runs and p.weeks_since_run is not None and p.weeks_since_run >= 4:
        out.append("Reprise de la course après plusieurs semaines sans courir : le plan remonte progressivement vers votre volume habituel.")
    if p.runs and not p.event and not p.target:
        out.append("Aucun objectif de course daté : ajoutez-le dans l'onglet Objectifs (nom, date, distance, dénivelé). "
                   "Le plan et la projection de faisabilité s'appuient dessus.")
    if p.event and p.event["distance_km"] == 0:
        out.append("Renseignez la distance de votre objectif pour obtenir une projection réaliste de votre préparation.")
    return out


def plan_weeks(p: Profile, today: date, weeks: int = 4, start: date | None = None, anchor: date | None = None) -> list[Session]:
    if p.red_flags:  # S1 : aucun plan d'intensité
        return []
    monday0 = _monday(start or today)  # la progression du bloc démarre à la première semaine générée
    weeks_to_event = max(0, (p.event["date"] - monday0).days // 7) if p.event else None
    weeks_to_target = max(0, (p.target["date"] - monday0).days // 7) if p.target else None
    event_near = weeks_to_event is not None and weeks_to_event <= 12  # C9 prime sur la trajectoire (C11) dans les 12 semaines d'un événement
    taper_wte = weeks_to_event if (event_near or weeks_to_target is None) else weeks_to_target
    ceiling = p.target_volume_min if (p.target and not event_near) else None
    anchor = anchor or monday0  # `anchor` : lundi du premier bloc, repris d'une génération à l'autre (G7)
    offset = max(0, (monday0 - anchor).days // 7)
    vols = weekly_volumes(p, weeks, taper_wte, offset, ceiling) if p.runs else []
    sessions: list[Session] = []
    for w in range(weeks):
        monday = monday0 + timedelta(days=7 * w)
        wk_to_event = None if weeks_to_event is None else weeks_to_event - w
        wk_to_target = None if weeks_to_target is None else weeks_to_target - w
        cyc = cycle_for(monday, anchor, p.deload_cycle, wk_to_event, wk_to_target, p.target["date"] if p.target else None)
        run_priority = wk_to_event is not None and wk_to_event <= 8 and p.event["distance_km"] > 0  # décision 3
        deload = vols[w][1] if vols else cyc.deload
        taper = vols[w][2] if vols else (wk_to_event is not None and 0 <= wk_to_event <= 1)
        week = _week(p, monday, w, vols[w][0] if vols else 0, deload, taper, run_priority, cyc)
        for s in week:
            s.details["cycle"] = cyc.as_dict()
        sessions += week
    return [s for s in sessions if s.date >= max(today, start or today)]


def _cd(a: int, b: int) -> int:
    """Distance circulaire entre deux jours de la semaine (la structure se répète d'une semaine à l'autre)."""
    return min((a - b) % 7, (b - a) % 7)


def _week(p: Profile, monday: date, w: int, run_min: float, deload: bool, taper: bool, run_priority: bool, cyc: Cycle) -> list[Session]:
    avail = [d for d in range(7) if d not in p.blocked]
    if len(avail) <= 1:
        return []
    n_days = min(p.days_per_week, len(avail) - 1)  # G5 : au moins un jour de repos
    placed: list[tuple[int, str, str]] = []  # (jour, type, variante)

    def on(d: int) -> list[str]:
        return [k for dd, k, _ in placed if dd == d]

    def feasible(d: int, kind: str) -> bool:
        if d not in avail or len(on(d)) >= 2:
            return False
        if d not in {x[0] for x in placed} and len({x[0] for x in placed}) >= n_days:
            return False
        if kind in KEY and any(k in KEY for k in on(d)):
            return False
        keys = [(dd, k) for dd, k, _ in placed if k in KEY]
        if kind in KEY and any(_cd(d, dd) < 2 for dd, _ in keys):  # G5 : 48 h entre séances clés
            return False
        runs_key = ("run_long", "run_quality")
        if kind == "strength_lower" and any(k in runs_key and _cd(d, dd) <= 1 for dd, k, _ in placed):  # I1, I2
            return False
        if kind in runs_key and any(k == "strength_lower" and _cd(d, dd) <= 1 for dd, k, _ in placed):
            return False
        if kind == "run_easy" and ("strength_lower" in on(d) or "run_quality" in on(d) or "run_easy" in on(d) or "run_long" in on(d)):
            return False
        if kind.startswith("strength") and any(k.startswith("strength") for k in on(d)):  # une seule séance de musculation par jour
            return False
        if kind == "strength_upper" and any(k == "strength_upper" and _cd(d, dd) < 2 for dd, k, _ in placed):
            return False
        if kind == "strength_crossfit" and any((k == "run_long" and _cd(d, dd) <= 1) or (k in KEY and dd == d) for dd, k, _ in placed):
            return False  # conditionnement intense : jamais la veille ou le lendemain de la sortie longue, ni le jour d'une séance clé
        if kind == "run_long" and any(k == "strength_crossfit" and _cd(d, dd) <= 1 for dd, k, _ in placed):
            return False
        if kind == "run_quality" and any(k == "strength_crossfit" and dd == d for dd, k, _ in placed):
            return False
        return True

    prefs = {"run_long": [5, 6, 0, 4], "run_quality": [1, 2, 3], "strength_lower": [2, 3, 1], "upper_a": [0, 1, 4], "upper_b": [2, 3, 4], "full": [1, 3, 5], "crossfit": [3, 2, 4, 1]}

    def place(kind: str, variant: str = "", order: list[int] | None = None) -> bool:
        pref_days = (p.run_days if kind.startswith("run_") else p.strength_days)
        order = order or prefs.get(variant or kind, avail)
        used = {x[0] for x in placed}
        best = None
        for d in avail:
            if not feasible(d, kind):
                continue
            rank = order.index(d) if d in order else len(order)
            stack = 0 if d not in used else (1 if kind == "run_easy" and "strength_upper" in on(d) else 4)  # I3 : footing + haut du corps possible
            cost = (0 if (not pref_days or d in pref_days) else 10) + rank + stack
            if best is None or cost < best[0]:
                best = (cost, d)
        if best is None:
            return False
        placed.append((best[1], kind, variant))
        return True

    # musculation : séances types
    n_str = min(p.strength_per_week, 3) if p.strength else 0
    if run_priority and p.event and p.event["distance_km"] >= 30:
        n_str = min(n_str, 2)  # décision 3 : sur un long événement la course l'emporte ; un événement court garde la fréquence choisie (jambes en entretien)
    variants: list[str] = []
    if n_str == 1:
        variants = ["full"]
    elif n_str == 2:
        variants = ["upper_a", "lower"] if (p.runs or not p.focus_upper) else ["upper_a", "upper_b"]
    elif n_str >= 3:
        variants = ["upper_a", "lower", "upper_b"]

    wod = p.crossfit and not run_priority and not taper and not (p.after_break and w < 2)  # M9 : la course l'emporte près de l'objectif
    if wod:
        if "upper_b" in variants:
            variants[variants.index("upper_b")] = "crossfit"
        elif "full" in variants:
            variants[variants.index("full")] = "crossfit"
        else:
            variants.append("crossfit")  # deux séances de musculation ou moins : le conditionnement s'ajoute
    quality_planned = False
    quality_ok = (p.runs and not deload and not taper and not p.run_injury and w >= 1 and run_min >= 120
                  and not (p.weeks_since_run is not None and p.weeks_since_run >= 4 and w < 3) and not (p.after_break and w < 3))
    if p.runs:
        place("run_long")
        if quality_ok:
            quality_planned = place("run_quality")
    for v in variants:
        if v == "lower":
            place("strength_lower", "lower")
        elif v == "upper_a":
            place("strength_upper", "upper_a")
    for v in variants:
        if v == "crossfit":
            if not place("strength_crossfit", "crossfit"):
                place("strength_upper", "upper_b")  # aucun jour compatible : séance de musculation à la place
        elif v == "upper_b":
            place("strength_upper", "upper_b")
        elif v == "full":
            place("strength_full", "full", prefs["full"])
    if p.runs:
        # footings en nombre suffisant pour porter le volume restant (≈ 60 min au plus chacun), jamais le jour de la sortie longue
        remaining = run_min - 0.30 * run_min - (0.22 * run_min if quality_planned else 0)
        n_easy = max(2 if (run_min >= 60 or p.days_per_week >= 4) else 1, -(-round(remaining) // min(60, p.weekday_max)))  # au moins 3 sorties avec 4 jours ou plus
        for _ in range(min(n_easy, 3)):
            place("run_easy", "", [d for d in avail if d != 4])

    # durées de course
    kinds = [k for _, k, _ in placed]
    n_easy_placed = kinds.count("run_easy")
    has_long, has_q = "run_long" in kinds, "run_quality" in kinds
    long_share = 0.30 if run_min >= 110 else 0.34  # très petit volume : trois sorties de durées proches
    ev_long = event_long_run(p, cyc.weeks_to_event, w) if has_long and not p.run_injury else None  # S2 : la sortie longue ne progresse plus
    if ev_long and deload:
        ev_long = max(round(ev_long * 0.75 / 5) * 5, 30)
    if ev_long:  # C9 : la sortie longue suit l'objectif ; les footings restent courts (2 × 25 min) pour limiter l'impact
        run_min = max(run_min, ev_long + (50 if n_easy_placed >= 2 else 25 * n_easy_placed))
    long_min = min(ev_long, p.weekend_max) if ev_long else (min(round(run_min * long_share), p.weekend_max) if has_long else 0)
    q_min = min(round(run_min * 0.22), p.weekday_max) if has_q else 0
    easy_min = min(round(max(run_min - long_min - q_min, 0) / n_easy_placed), p.weekday_max) if n_easy_placed else 0
    easy_min = max(easy_min, 20) if n_easy_placed else 0
    capacity = q_min + easy_min * n_easy_placed
    if capacity and long_min and run_min >= 110 and not ev_long:
        long_min = min(long_min, round(capacity * 0.42))  # C2 : ≤ 30 % du volume réel
    long_min = max(long_min, 25) if has_long else 0

    notes = ["Semaine allégée (G2)."] if deload else (["Affûtage avant l'objectif (C6)."] if taper else [])
    if p.run_injury:
        notes.append("Douleur déclarée sur une zone qui porte la course : le volume et l'intensité ne montent pas (S2). "
                     "Si elle persiste ou augmente, consultez un professionnel de santé.")
    out = []
    for d, kind, variant in sorted(placed):
        out.append(_make(p, kind, variant, monday + timedelta(days=d), w, long_min, q_min, easy_min, deload, taper, run_priority, notes, cyc))
    return out


def _make(p: Profile, kind: str, variant: str, day: date, w: int, long_min: int, q_min: int, easy_min: int, deload: bool, taper: bool,
          run_priority: bool, notes: list[str], cyc: Cycle) -> Session:
    if kind == "run_long":
        d: dict[str, Any] = {"zone": zone_text(p, "easy")}
        ev = None if p.run_injury else event_long_run(p, cyc.weeks_to_event, w)
        rules_long = ["C2", "C1", "G1"] + (["G2"] if deload else []) + (["S2"] if p.run_injury else [])
        sess_notes = list(notes)
        if ev and p.event:
            rules_long = ["C9", "C1"] + (["G2"] if deload else [])
            elev = float(p.event.get("elevation_m") or 0)
            if p.trail and elev > 0:
                d["vert_m"] = round(elev * 0.8 * min(1.0, long_min / max(event_long_peak(p), 1)) / 10) * 10
            sess_notes.append(f"Préparation de {p.event['title']} : sortie longue progressive vers {event_long_peak(p)} min ; alternez marche et course dans les côtes, allure de conversation.")
        elif p.trail and p.weekly_vert > 0:
            d["vert_m"] = round(p.weekly_vert * (1 if p.run_injury else 1.1 ** (w + 1)) * 0.5 / 10) * 10
        return Session(day, kind, "Sortie longue" + (" (trail)" if p.trail else ""), long_min, d, rules_long, sess_notes)
    if kind == "run_quality":
        tq = T.quality_session(cyc.macro, q_min, p.target, p.level_min, day - timedelta(days=day.weekday()), p.today)
        if tq:  # C11 : séances de la trajectoire (seuil, puis allure de l'objectif)
            title = "Séance de qualité (seuil)" if cyc.macro == "threshold" else "Séance de qualité (allure de l'objectif)"
            return Session(day, kind, title, q_min, {"zone": zone_text(p, "quality"), "format": tq["format"]}, ["C1", "C11", "G5"], list(notes))
        reps = 4 + min(cyc.block_no + cyc.week_in_block - 1, 4)  # M8 : une répétition de plus d'un bloc à l'autre
        d = {"zone": zone_text(p, "quality"), "format": f"{reps} × 3 min soutenu, 2 min trot" if not p.trail
             else f"{reps} × 2 min de côte, descente en trottinant"}
        return Session(day, kind, "Séance de qualité" + (" (côtes)" if p.trail else ""), q_min, d, ["C1", "G5"] + (["C5"] if p.trail else []), list(notes))
    if kind == "run_easy":
        return Session(day, kind, "Footing facile", easy_min, {"zone": zone_text(p, "easy")}, ["C1"] + (["S2"] if p.run_injury else []), list(notes))
    if kind == "strength_crossfit":
        minutes, det, cf_notes = CF.build(cyc, p.level, p.injuries)
        return Session(day, kind, "Séance CrossFit" + (" (allégée)" if cyc.deload else ""), minutes, det, ["M9", "G5"], list(notes) + cf_notes)
    maint = run_priority or taper
    n_build = p.deload_cycle - 1
    slots = S.session_plan(variant, maint, build=min(cyc.week_in_block - 1, n_build - 1), n_build=n_build, deload=deload or taper, block=cyc.block_no)
    if run_priority and variant != "lower" and not (deload or taper):  # course proche : un peu moins d'accessoires
        for sl in slots:
            if sl["role"] == "accessory":
                sl["sets"] = str(max(2, int(sl["sets"]) - 1))
    title = S.TITLES[variant] + (" (entretien)" if maint and variant == "lower" else "")
    rules = ["M1" if not maint else "M2", "M3", "M5", "M7"] + (["M6"] if p.focus_upper else []) + (["I1", "I2"] if kind == "strength_lower" else [])
    n = len(slots)
    sess_notes = list(notes)
    if kind == "strength_lower":
        sess_notes.append("Priorité course : les jambes restent en entretien (force, pas d'épuisement)." if maint else
                          "Jambes une fois par semaine : force, loin des séances de course clés.")
    sess_notes.append("Progression : quand vous atteignez le haut de la fourchette sur toutes les séries, ajoutez 2,5 kg (haut du corps) ou 5 kg (jambes).")
    return Session(day, kind, title, 35 + 6 * n, {"variant": variant, "slots": slots}, rules, sess_notes)
