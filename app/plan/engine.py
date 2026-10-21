"""Moteur de plan déterministe (règles : docs/rules.md). Aucun appel externe, aucune aléa."""
from __future__ import annotations

import math
import re
from dataclasses import dataclass, field
from datetime import date, timedelta
from typing import Any

from app.plan import crossfit as CF
from app.plan import hybrid as HB
from app.plan import hyrox as HY
from app.plan import injuries as INJ
from app.plan import strength as S
from app.plan import trajectory as T
from app.plan.cycles import Cycle, cycle_for

DAYS = ["lundi", "mardi", "mercredi", "jeudi", "vendredi", "samedi", "dimanche"]
DEFAULT_EASY_PACE = 6.5  # min/km si aucune donnée
GROWTH_STEP = 1.08  # G1 : montée ≤ 10 % par semaine
TAPER_FACTOR = 0.6  # C6 : affûtage à 60 % du volume de la dernière semaine de montée
UNDER_DELIVERY = 0.97  # G11 : une semaine qui n'atteint pas 97 % du volume visé sert de base à la suivante
CAP_TOLERANCE = 1.1  # G6 : la durée d'une séance de musculation est une estimation (35 min + 6 min par exercice), respectée à 10 % près
LAYOFF_WEEKS = 4  # G8 : nombre de semaines sans course à partir duquel la reprise (G3) s'applique même sans historique mesuré
RETURN_GROWTH_MAX = 1.15  # G3 : reprise après arrêt, retour au niveau habituel en 4 à 6 semaines
DELOAD_FACTOR = 0.65  # G2 : semaine allégée (−35 %)
KEY = {"run_long", "run_quality", "strength_lower"}
RUN_ZONES = {"genou", "cheville", "hanche", "tibia", "tendon d'Achille", "mollet", "pied", "ischio-jambiers"}  # S2 : zones qui portent la course


@dataclass
class Profile:
    runs: bool = False
    strength: bool = False
    crossfit: bool = False  # sport déclaré : une séance de conditionnement par semaine (M9)
    hybrid: str | None = None  # "hyrox" | "crossfit" : sport hybride déclaré (Hyrox l'emporte si les deux le sont)
    dedicated: bool = False  # hybride sans course déclarée : la semaine est entièrement construite autour du sport hybride (M10, M18)
    hy_level: str = "débutant"  # niveau pour les séances hybrides (années de pratique, expérience Hyrox ; à défaut le niveau de musculation)
    hy_std: dict[str, int] = field(default_factory=dict)  # charges officielles de la catégorie Hyrox visée (M19)
    hy_weak: set[str] = field(default_factory=set)  # stations jugées faibles : travaillées en premier
    skills: set[str] = field(default_factory=set)
    has_gear: bool = True  # traîneau et SkiErg à disposition
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
    injury_unknown: list[str] = field(default_factory=list)  # blessures écrites en texte libre que le moteur ne sait pas rattacher à une zone (S7)
    notices: list[str] = field(default_factory=list)  # entrées corrigées ou incohérentes, affichées avec le plan (S8)
    no_days: bool = False  # 0 jour d'entraînement déclaré : aucun plan (S8)
    caps_declared: bool = False  # durée maximale de séance saisie par l'utilisateur (G6) : les séances de musculation sont raccourcies pour la respecter
    red_flags: bool = False
    run_injury: bool = False  # blessure active sur une zone qui porte la course : volume et intensité gelés (S2)
    event: dict[str, Any] | None = None  # {"date": date, "title": str, "distance_km": float, "elevation_m": float}
    deload_cycle: int = 4  # 3+1 par défaut (2+1 : 3)
    facts: dict[str, Any] = field(default_factory=dict)
    today: date = field(default_factory=date.today)
    target: dict[str, Any] | None = None  # objectif de performance daté (trajectoire, C11) : {"date", "title", "distance_km", "time_min"}
    level_min: float | None = None  # temps équivalent actuel sur la distance de l'objectif (C10)
    target_volume_min: float | None = None  # plafond de volume hebdomadaire de course (minutes) tant que l'objectif est lointain (C12)


def _strs(v: Any) -> list[str]:
    """Liste de textes d'un fait : une chaîne seule compte pour une valeur, ce qui n'est pas du texte est écarté."""
    if isinstance(v, str):
        return [v]
    return [x for x in v if isinstance(x, str)] if isinstance(v, list | tuple | set) else []


def _days(v: Any) -> set[int]:
    return {DAYS.index(d) for d in (INJ.fold(x) for x in _strs(v)) if d in DAYS}


MIN_SESSION_MIN = 20  # en dessous, une séance utile n'existe pas : la durée maximale saisie est relevée à 20 minutes
MAX_SESSION_MIN = 600
MAX_WEEKLY_KM = 300.0
MIN_EASY_PACE, MAX_EASY_PACE = 3.5, 12.0  # min/km : hors de ces bornes, le record 10 km saisi est incohérent


DURATION_BAD = ("La durée maximale de séance en semaine est nulle ou illisible : la durée par défaut est utilisée. Indiquez votre durée réelle dans vos réponses (Contraintes).",
                "La durée maximale de séance le week-end est nulle ou illisible : la durée par défaut est utilisée. Indiquez votre durée réelle dans vos réponses (Contraintes).")
DURATION_SHORT = ("La durée maximale de séance en semaine est inférieure à 20 minutes : 20 minutes sont retenues (G6).",
                  "La durée maximale de séance le week-end est inférieure à 20 minutes : 20 minutes sont retenues (G6).")


def _sanitize_availability(p: Profile, facts: dict[str, Any]) -> None:
    """Jours et durées d'entraînement : valeurs absurdes ramenées à la plage de sécurité, jamais d'exception, message affiché avec le plan (S8, G5, G6)."""
    raw = facts.get("constraints.training_days")
    n = _num(raw, -1)
    if raw is None:
        p.days_per_week = 3
    elif n < 0:
        p.days_per_week = 3
        p.notices.append("Le nombre de jours d'entraînement n'est pas lisible : 3 jours par semaine sont utilisés. Corrigez-le dans vos réponses (Contraintes).")
    elif n == 0:
        p.no_days, p.days_per_week = True, 2
        p.notices.append("Vous avez indiqué 0 jour d'entraînement par semaine : aucun plan n'est créé. Indiquez au moins 2 jours dans vos réponses (Contraintes).")
    elif n < 2:
        p.days_per_week = 2
        p.notices.append("Moins de 2 jours d'entraînement indiqués : le plan en propose 2 au minimum. Vous pouvez les modifier dans vos réponses (Contraintes).")
    elif n > 6:
        p.days_per_week = 6
        p.notices.append("Plus de 6 jours d'entraînement indiqués : le plan en propose 6 au plus, pour garder un jour de repos par semaine (G5)." if n <= 7 else
                         "Une semaine compte 7 jours : le plan en propose 6 au plus, pour garder un jour de repos (G5). Corrigez-le dans vos réponses (Contraintes).")
    else:
        p.days_per_week = int(n)
    for key, bad, short in (("constraints.weekday_session_max_min", DURATION_BAD[0], DURATION_SHORT[0]), ("constraints.weekend_session_max_min", DURATION_BAD[1], DURATION_SHORT[1])):
        raw = facts.get(key)
        v = _num(raw, 0.0)
        if raw is not None and v <= 0:
            p.notices.append(bad)
        elif 0 < v < MIN_SESSION_MIN:
            p.notices.append(short)
        if key.endswith("weekday_session_max_min"):
            p.weekday_max = int(min(max(v, MIN_SESSION_MIN), MAX_SESSION_MIN)) if v > 0 else 60
            p.caps_declared = v > 0
        else:
            p.weekend_max = int(min(max(v, MIN_SESSION_MIN), MAX_SESSION_MIN)) if v > 0 else max(p.weekday_max, 120)


def _num(v: Any, default: float = 0.0) -> float:
    """Nombre fini ou valeur par défaut (texte, booléen, NaN et infini sont écartés)."""
    if not isinstance(v, int | float) or isinstance(v, bool):
        return default
    try:
        return float(v) if math.isfinite(v) else default
    except OverflowError:  # entier démesuré
        return default


def hybrid_level(facts: dict[str, Any]) -> str:
    """Niveau hybride (M15) : années de CrossFit et expérience Hyrox si renseignées, sinon niveau de musculation déclaré, sinon débutant."""
    years, done = _num(facts.get("hybrid.crossfit_years")), facts.get("hybrid.hyrox_done")
    if facts.get("hybrid.crossfit_years") is not None or done:
        return "avancé" if (years >= 3 or done == "plusieurs fois") else ("intermédiaire" if (years >= 1 or done == "une fois") else "débutant")
    declared = facts.get("strength.level")
    return declared if declared in HB.LEVELS else "débutant"


def build_profile(facts: dict[str, Any], goals: list[dict[str, Any]], today: date) -> Profile:
    sports = set(_strs(facts.get("sports.practiced")))
    p = Profile(facts=facts, today=today)
    p.runs = bool(sports & {"running", "trail"})
    p.trail = "trail" in sports
    p.strength = "strength" in sports
    p.crossfit = bool(sports & {"crossfit", "hyrox"})
    p.hybrid = "hyrox" if "hyrox" in sports else ("crossfit" if "crossfit" in sports else None)
    p.dedicated = p.hybrid is not None and not p.runs
    p.hy_level = hybrid_level(facts)
    p.hy_std = HY.standard_for(facts.get("hybrid.hyrox_category"), facts.get("body.sex_for_calc"))
    p.hy_weak = HY.weak_keys(facts.get("hybrid.hyrox_weak_stations"))
    p.skills = set(_strs(facts.get("hybrid.crossfit_skills")))
    p.has_gear = facts.get("hybrid.access") not in ("garage ou salle perso", "aucun lieu fixe")
    _sanitize_availability(p, facts)
    p.blocked = _days(facts.get("multisport.blocked_days"))
    p.run_days = _days(facts.get("multisport.preferred_run_days"))
    p.strength_days = _days(facts.get("multisport.preferred_strength_days"))
    p.weekly_km = min(max(_num(facts.get("running.weekly_km_8w")), 0.0), MAX_WEEKLY_KM)
    p.usual_km = min(max(_num(facts.get("running.weekly_km_12m")), 0.0), MAX_WEEKLY_KM)
    ws = _num(facts.get("running.weeks_since_last_run"), -1)
    p.weeks_since_run = min(int(ws), 520) if ws >= 0 else None
    p.longest_min = min(max(_num(facts.get("running.longest_recent_min")), 0.0), 600.0)
    best10 = _num(facts.get("running.best_10k_min"))
    if best10 > 0:
        pace = round(best10 / 10 * 1.25, 2)  # allure facile ≈ allure 10 km × 1,25
        p.easy_pace = min(max(pace, MIN_EASY_PACE), MAX_EASY_PACE)
        if p.easy_pace != pace:
            p.notices.append("Le record 10 km saisi paraît incohérent : une allure plausible est utilisée. Vérifiez-le dans vos réponses (Course).")
    hr = _num(facts.get("running.hr_max"))
    p.hr_max = int(hr) if hr >= 140 else None
    declared = round(min(max(_num(facts.get("strength.sessions_per_week"), 2), 0.0), 14)) or 2
    measured = round(min(max(_num(facts.get("strength.sessions_per_week_12m")), 0.0), 14))  # fréquence réelle (Garmin) : le plan ne descend pas en dessous
    p.strength_per_week = max(1, min(4, max(declared, measured)))
    lv = facts.get("strength.level")
    p.level = lv if isinstance(lv, str) and lv in HB.LEVELS else "débutant"
    focus = set(_strs(facts.get("goal.physique_focus")))
    p.focus_upper = bool(focus & {"haut du corps", "épaules", "dos", "pectoraux", "bras"})
    p.cutting = facts.get("goal.weight_direction") == "perdre"
    by = _num(facts.get("body.birth_year"))
    p.age = today.year - int(by) if by and 10 <= today.year - by <= 110 else None  # une année de naissance absurde n'ôte ni n'ajoute de prudence
    p.weekly_vert = min(max(_num(facts.get("trail.weekly_vert_m")), 0.0), 20000.0)
    p.after_break = facts.get("history.recent_break") in ("oui blessure", "oui autre raison")
    p.injuries, p.injury_unknown = INJ.normalize_injuries(facts)  # S2, S7 : texte libre, anglais, accents, pluriels
    p.run_injury = bool(p.injuries & RUN_ZONES)
    flags = set(facts.get("health.red_flags") or []) - {"aucun"}
    p.red_flags = bool(flags) and facts.get("health.red_flags_discussed") != "oui"
    if (p.age and p.age > 45) or p.after_break:
        p.deload_cycle = 3  # G2 : 2+1
    active = [g for g in goals if g.get("status") == "active" and g.get("kind") == "event" and isinstance(g.get("target_date"), date)]
    for g in sorted((g for g in active if today - timedelta(days=90) <= g["target_date"] < today), key=lambda g: g["target_date"], reverse=True)[:1]:  # la plus récente
        title = str(g.get("title", ""))
        p.notices.append(f"L'échéance « {title} » est passée : elle n'est plus prise en compte. Mettez-la à jour ou clôturez-la dans l'onglet Objectifs.")
    events = [g for g in active if g["target_date"] >= today]
    if events:
        events.sort(key=lambda g: ({"principal": 0, "important": 1}.get(g.get("priority"), 2), g["target_date"], str(g.get("title", ""))))
        e = {**events[0], "title": str(events[0].get("title", ""))}
        same_day = [g for g in events[1:] if g["target_date"] == e["target_date"]]
        if same_day:
            title, other = e["title"], str(same_day[0].get("title", ""))
            p.notices.append(f"Deux objectifs tombent le même jour : « {title} » (le plus prioritaire) structure le plan, « {other} » n'est pas préparé séparément.")
        d = e.get("details") if isinstance(e.get("details"), dict) else {}
        hyrox_ev = "hyrox" in e["title"].lower() or str(d.get("sport", "")).lower() == "hyrox"
        dist = 0.0 if hyrox_ev else _num(d.get("distance_km"))  # Hyrox : les 8 km de course sont dans l'épreuve, pas un objectif de course (M21)
        if not dist and not hyrox_ev:  # « Trail 50 km » : distance déduite du titre quand elle n'est pas renseignée
            m = re.search(r"(\d+(?:[.,]\d+)?)\s*km", e["title"], re.I)
            dist = float(m.group(1).replace(",", ".")) if m else 0.0
        p.event = {"date": e["target_date"], "title": e["title"], "distance_km": dist, "elevation_m": _num(d.get("elevation_m")), "hyrox": hyrox_ev}
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
    layoff = p.weeks_since_run is not None and p.weeks_since_run >= LAYOFF_WEEKS
    if layoff:  # G8 : sans course depuis 4 semaines ou plus, le volume déclaré ou par défaut date d'avant l'arrêt : G3 s'applique à lui
        start = max((0.5 if p.weeks_since_run <= LAYOFF_WEEKS else 0.3) * usual, 75 if usual >= 150 else 45)
    elif measured >= 0.6 * usual:
        start = measured
    else:
        frac = 0.5 if (p.weeks_since_run is not None and p.weeks_since_run <= 4) else 0.3
        start = max(measured, frac * usual, 75 if usual >= 150 else 45)
    if p.after_break and not layoff and measured >= 0.6 * usual:
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
            v = last_build * TAPER_FACTOR
        else:
            if last_build < usual:  # G3 : reprise en 4 à 6 semaines, sans dépasser le volume d'avant l'arrêt avant la fin de la reprise (G8)
                v = min(last_build * max(min(RETURN_GROWTH_MAX, (usual / max(start, 1)) ** (1 / 5)), GROWTH_STEP), usual, cap_run)
            else:
                v = min(last_build * GROWTH_STEP, cap_run)
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


def warnings(p: Profile) -> list[str]:
    """Entrées corrigées, disponibilités insuffisantes, blessure non reconnue : ce que le plan a dû adapter et le dit (S7, S8, G5, G6, G9)."""
    out = list(p.notices)
    usable = 7 - len(p.blocked)
    if not p.no_days and usable >= 2 and min(p.days_per_week, usable - 1) < p.days_per_week:
        k = min(p.days_per_week, usable - 1)
        out.append(f"Vous avez indiqué {p.days_per_week} jours d'entraînement, mais vos jours bloqués n'en laissent que {usable} : "
                   f"le plan en propose {k} au plus, un jour de repos étant gardé (G5, G6).")
    if usable < 2 and not p.no_days:
        out.append("Vos jours bloqués ne laissent aucun jour d'entraînement : au moins 2 jours libres sont nécessaires pour garder un jour de repos (G5, G6). "
                   "Libérez un jour dans vos réponses (Multisport).")
    elif usable - 1 < 3 and not p.no_days:
        out.append("Vos jours bloqués laissent moins de 3 séances possibles par semaine : le plan garde l'essentiel (sortie longue, séance clé, musculation) dans cet ordre (G9). "
                   "Libérez un jour pour un plan plus complet.")
    return out + _injury_notes(p)


def empty_reason(p: Profile) -> str:
    """Pourquoi aucune séance n'a été créée."""
    if p.red_flags:
        return "Un signal d'alerte à l'effort doit d'abord être discuté avec un médecin."
    if p.no_days:
        return "Vous avez indiqué 0 jour d'entraînement par semaine : indiquez au moins 2 jours dans vos réponses (Contraintes)."
    if not (p.runs or p.strength or p.hybrid):
        return "Choisissez au moins la course ou la musculation dans vos sports pour obtenir un plan."
    if 7 - len(p.blocked) < 2:
        return "Vos jours bloqués ne laissent aucun jour d'entraînement : au moins 2 jours libres sont nécessaires pour garder un jour de repos (G5). Libérez un jour dans vos réponses (Multisport)."
    return "Aucune séance ne tient dans les jours restants : vérifiez vos jours bloqués et vos durées maximales (Contraintes, Multisport)."


def advice(p: Profile) -> list[str]:
    """Conseils d'organisation (non bloquants) affichés avec le plan."""
    out = warnings(p)
    if p.strength and p.focus_upper and p.strength_per_week < 3:
        out.append("Pour développer le haut du corps, 3 séances de musculation par semaine permettent de le travailler deux fois, "
                   "avec les jambes en entretien. Vous pouvez passer à 3 dans vos réponses (Musculation, fréquence).")
    if p.runs and p.weeks_since_run is not None and p.weeks_since_run >= 4:
        out.append("Reprise de la course après plusieurs semaines sans courir : le plan remonte progressivement vers votre volume habituel.")
    if p.runs and not p.event and not p.target:
        out.append("Aucun objectif de course daté : ajoutez-le dans l'onglet Objectifs (nom, date, distance, dénivelé). "
                   "Le plan et la projection de faisabilité s'appuient dessus.")
    if p.event and p.event["distance_km"] == 0 and not p.event.get("hyrox"):
        out.append("Renseignez la distance de votre objectif pour obtenir une projection réaliste de votre préparation.")
    return out


def plan_weeks(p: Profile, today: date, weeks: int = 4, start: date | None = None, anchor: date | None = None) -> list[Session]:
    if p.red_flags or p.no_days:  # S1 : aucun plan d'intensité ; S8 : 0 jour d'entraînement déclaré
        return []
    monday0 = _monday(start or today)  # la progression du bloc démarre à la première semaine générée
    weeks_to_event = max(0, (p.event["date"] - monday0).days // 7) if p.event else None
    weeks_to_target = max(0, (p.target["date"] - monday0).days // 7) if p.target else None
    event_near = weeks_to_event is not None and weeks_to_event <= 12  # C9 prime sur la trajectoire (C11) dans les 12 semaines d'un événement
    taper_wte = weeks_to_event if (event_near or weeks_to_target is None) else weeks_to_target
    ceiling = p.target_volume_min if (p.target and not event_near) else None
    anchor = anchor or monday0  # `anchor` : lundi du premier bloc, repris d'une génération à l'autre (G7)
    offset = max(0, (monday0 - anchor).days // 7)
    vols = weekly_volumes(p, weeks, taper_wte, offset, ceiling) if (p.runs or (p.dedicated and p.hybrid == "hyrox")) else []
    sessions: list[Session] = []
    last_eff: float | None = None  # G11 : volume réellement planifié de la dernière semaine de montée, quand il est inférieur à celui visé
    growth = RETURN_GROWTH_MAX if (p.after_break or (p.weeks_since_run or 0) >= LAYOFF_WEEKS) else GROWTH_STEP
    for w in range(weeks):
        monday = monday0 + timedelta(days=7 * w)
        wk_to_event = None if weeks_to_event is None else weeks_to_event - w
        wk_to_target = None if weeks_to_target is None else weeks_to_target - w
        cyc = cycle_for(monday, anchor, p.deload_cycle, wk_to_event, wk_to_target, p.target["date"] if p.target else None)
        run_priority = wk_to_event is not None and wk_to_event <= 8 and p.event["distance_km"] > 0 and not p.dedicated  # décision 3
        deload = vols[w][1] if vols else cyc.deload
        taper = vols[w][2] if vols else (wk_to_event is not None and 0 <= wk_to_event <= 1)
        budget = vols[w][0] if vols else 0
        guided = bool(p.event and p.runs and p.event["distance_km"] > 0 and wk_to_event is not None and 0 < wk_to_event <= 12)  # C9 dépasse volontairement G1
        if last_eff is not None and not guided:
            budget = min(budget, last_eff * (DELOAD_FACTOR if deload else TAPER_FACTOR if taper else growth))
        week = _week(p, monday, w, budget, deload, taper, run_priority, cyc)
        if vols and not (deload or taper):
            done = _run_total(week)
            last_eff = done if 0 < done < UNDER_DELIVERY * budget else float(max(budget, done))
        for s in week:
            s.details["cycle"] = cyc.as_dict()
        sessions += week
    return [s for s in _around_event(p, sessions) if s.date >= max(today, start or today)]


def _run_total(week: list[Session]) -> float:
    """Minutes de course d'une semaine, y compris la course des séances hybrides (G1, G11)."""
    return float(sum(s.duration_min for s in week if s.kind.startswith("run_")) + sum(_num(s.details.get("run_min")) for s in week if s.kind == HB.KIND))


def _around_event(p: Profile, sessions: list[Session]) -> list[Session]:
    """Le jour de l'événement est la séance : rien d'autre ce jour-là, ni de course les 2 jours suivants (récupération). La veille : 30 min de course au plus, pas de jambes (C6)."""
    if not p.event:
        return sessions
    ev = p.event["date"]
    out = []
    for s in sessions:
        delta = (ev - s.date).days
        hyrox = bool(p.event.get("hyrox"))  # M21 : la veille et les 2 jours suivants un Hyrox, ni séance dure ni jambes lourdes
        if delta == 0 or (-2 <= delta < 0 and (s.kind.startswith("run_") or (hyrox and s.kind in ("strength_crossfit", "strength_lower")))):
            continue
        if delta == 1:
            if s.kind == "strength_lower" or (hyrox and s.kind == "strength_crossfit"):
                continue
            if s.kind.startswith("run_"):
                s.duration_min = min(s.duration_min, 30)
                if s.kind == "run_quality":
                    s.kind, s.title = "run_easy", "Footing facile"
                s.details = {k: v for k, v in s.details.items() if k not in ("format", "vert_m")}
        out.append(s)
    return out


def _cd(a: int, b: int) -> int:
    """Distance circulaire entre deux jours de la semaine (la structure se répète d'une semaine à l'autre)."""
    return min((a - b) % 7, (b - a) % 7)


HARD_HY = {"hy_stations", "hy_comp", "hy_sim", "hy_half"}
HY_VARIANTS = HARD_HY | {"crossfit", "cf_gym"}
HY_SIM = {"full": "hy_sim", "half": "hy_half"}


def hy_pace(p: Profile) -> float:
    """Allure de course Hyrox visée : un peu plus lente que l'allure du 10 km (≈ allure facile ÷ 1,25 × 1,10) ; pratique de terrain, pas un résultat établi (M20)."""
    return round(p.easy_pace / 1.25 * 1.10, 2)


def _cap(p: Profile, day: date) -> int:
    return p.weekend_max if day.weekday() >= 5 else p.weekday_max


def _hctx(p: Profile, cyc: Cycle, light: bool, day: date, taper: bool = False) -> HB.Ctx:
    return HB.Ctx(cyc=cyc, level=p.hy_level, injuries=p.injuries, skills=p.skills, cap=_cap(p, day), light=light, run_injury=p.run_injury, pace=hy_pace(p), std=p.hy_std,
                  weak=p.hy_weak, has_gear=p.has_gear, hr_max=p.hr_max, taper=taper)


def _sim_week(p: Profile, cyc: Cycle, run_min: float, taper: bool) -> str | None:
    """Simulation Hyrox de la semaine (M21) ; abandonnée si sa course dépasse la moitié du volume de course (G1)."""
    if p.hybrid != "hyrox" or taper:
        return None
    sim = HY.sim_plan(cyc, bool(p.event and p.event.get("hyrox")), p.event is not None)
    if sim == "full" and 8 * hy_pace(p) > 0.5 * run_min:
        sim = "half"
    if sim == "half" and 4 * hy_pace(p) > 0.5 * run_min:
        sim = None
    return sim


DROPPED = {
    "run_long": "La sortie longue n'a pas pu être placée : vos jours disponibles ne laissent pas 48 h avec les autres séances clés ni d'écart avec les jambes (G5, I1, I2). "
                "Libérez un jour pour la retrouver.",
    "run_quality": "La séance de qualité n'a pas pu être placée : vos jours disponibles ne laissent pas 48 h avec les autres séances clés (G5, I2). Libérez un jour pour la retrouver.",
    "lower": "La séance de jambes n'a pas pu être placée : vos jours disponibles ne l'écartent pas assez des séances de course clés (G5, I1, I2). Libérez un jour pour la retrouver.",
    "upper": "Une séance de haut du corps n'a pas pu être placée : vos jours disponibles sont trop peu nombreux ou trop rapprochés (G5, M14). Libérez un jour pour la retrouver.",
    "full": "La séance de musculation n'a pas pu être placée : vos jours disponibles sont trop peu nombreux (G5). Libérez un jour pour la retrouver.",
    "hybrid": "La séance de conditionnement (CrossFit ou Hyrox) n'a pas pu être placée : aucun jour ne la sépare de 48 h des autres séances dures (G5, I7, M14). "
              "Elle saute cette semaine ; libérez un jour pour la retrouver.",
    "crossfit_replaced": "La séance CrossFit n'a trouvé aucun jour compatible avec la course et la musculation (G5, I7, M14) : elle est remplacée par une séance de haut du corps.",
    "cap": "Une séance ne tient pas dans votre durée maximale et saute cette semaine (G6) : augmentez la durée maximale de séance pour la retrouver.",
    "dedicated": "Vos jours disponibles ne permettent pas d'alterner séances dures et faciles pour toutes les séances voulues (G5, M14) : la dernière saute cette semaine. "
                 "Libérez un jour pour la retrouver.",
}


def _injury_notes(p: Profile) -> list[str]:
    """S7 : une blessure écrite en texte libre que le moteur ne sait pas rattacher à une zone n'est pas oubliée en silence."""
    if not p.injury_unknown:
        return []
    text = ", ".join(p.injury_unknown[:3])
    return [f"Blessure déclarée (« {text} ») que le plan ne sait pas rattacher à une zone : aucun exercice n'est exclu automatiquement (S7). "
            "Choisissez des mouvements sans douleur et consultez un professionnel de santé si elle persiste."]


def _enforce_caps(p: Profile, sessions: list[Session]) -> list[Session]:
    """G6 : aucune séance ne dépasse la durée maximale du jour. Les courses sont raccourcies ; une séance de conditionnement qui ne tient pas saute, et c'est dit."""
    kept: list[Session] = []
    cut = False
    for s in sessions:
        cap = _cap(p, s.date)
        if s.duration_min > cap and s.kind.startswith("run_"):
            s.duration_min = cap
        elif s.kind == "strength_crossfit" and s.duration_min > cap or s.kind.startswith("strength_") and s.duration_min > cap * CAP_TOLERANCE:
            cut = True  # le minimum d'une séance utile ne tient pas dans une durée si courte
            continue
        kept.append(s)
    if cut:
        for s in kept:
            s.notes.append(DROPPED["cap"])
    return kept


def _week_dedicated(p: Profile, monday: date, w: int, run_min: float, deload: bool, taper: bool, cyc: Cycle) -> list[Session]:
    """Semaine d'un sportif hybride sans course déclarée (M10 CrossFit, M18 Hyrox) : créneaux distincts, jamais deux jours durs d'affilée sur les mêmes groupes (M14)."""
    avail = [d for d in range(7) if d not in p.blocked]
    if len(avail) <= 1:
        return []
    n_days = min(p.days_per_week, len(avail) - 1)  # G5 : au moins un jour de repos
    hyrox = p.hybrid == "hyrox"
    light = deload or taper or (p.after_break and w < 2)
    notes = ["Semaine allégée (G2)."] if deload else (["Affûtage avant l'objectif (C6)."] if taper else [])
    if p.run_injury and hyrox:
        notes.append("Douleur déclarée sur une zone qui porte la course : le volume et l'intensité de course ne montent pas (S2). Si elle persiste ou augmente, consultez un professionnel de santé.")
    sim = _sim_week(p, cyc, run_min, taper) if hyrox else None
    keys = HY.hy_keys(n_days) if hyrox else HB.crossfit_keys(n_days, light, p.injuries)
    quality_ok = (hyrox and run_min >= 75 and not deload and not taper and not p.run_injury and w >= 1
                  and not (p.weeks_since_run is not None and p.weeks_since_run >= 4 and w < 3) and not (p.after_break and w < 3))
    if hyrox and not quality_ok:
        keys = ["hy_run_z2b" if k == "hy_run_q" else k for k in keys]
    if hyrox and cyc.macro == "race":  # semaine de l'épreuve : footing et activation seulement
        keys = [k for k in keys if k in ("hy_run_z2", "hy_run_z2b", "hy_stations")][:3]
    placed, kept = HB.assign(keys, avail, n_days, lighten=light)
    if len(kept) < len(keys):  # G9 : aucune disposition ne respecte l'alternance dur/facile (M14) : les séances retirées sont dites
        notes.append(DROPPED["dedicated"])
    notes += _injury_notes(p)
    out: list[Session] = []
    if hyrox:
        variants = {}
        for k in kept:
            if k == "hy_comp":
                variants[k] = HY_SIM.get(sim or "", "hy_comp")
            elif k == "hy_stations":
                alt = "hy_comp" if ((cyc.week_in_block - 1) % 2 == 1 and cyc.macro != "race") else "hy_stations"
                variants[k] = HY_SIM.get(sim or "", alt) if "hy_comp" not in kept else "hy_stations"
        built, hy_run = {}, 0.0
        for k, var in variants.items():
            day = monday + timedelta(days=placed[k])
            res, got = HY.build_station_variant(var, _hctx(p, cyc, light, day, taper), run_min)
            built[k] = (res, got)
            hy_run += res[1].get("run_min", 0)
        others = max(run_min - hy_run, 0.35 * run_min)
        n_easy = sum(1 for k in kept if k.startswith("hy_run_z2"))
        has_q = "hy_run_q" in kept
        q_min = min(max(round(others * 0.35), 25), p.weekday_max) if has_q else 0
        easy_min = max(min(round((others - q_min) / n_easy), p.weekday_max), 20) if n_easy else 0
        if has_q and not n_easy:
            q_min = min(round(others), p.weekday_max)
    for k in sorted(kept, key=lambda x: placed[x]):
        day = monday + timedelta(days=placed[k])
        if k.startswith("cf_"):
            ctx = _hctx(p, cyc, light, day, taper)
            minutes, det, nts, rules = HB.build(k, ctx)
            out.append(Session(day, HB.KIND, HB.TITLES[k] + (" (allégée)" if light else ""), minutes, det, rules, notes + nts))
        elif k == "hy_run_q":
            ctx = _hctx(p, cyc, light, day, taper)
            out.append(Session(day, "run_quality", "Séance de qualité (Hyrox)", q_min, {"zone": zone_text(p, "quality"), "format": HY.quality_format(ctx, q_min)},
                               ["C1", "G5", "M18"], list(notes)))
        elif k.startswith("hy_run_z2"):
            out.append(Session(day, "run_easy", "Footing facile", easy_min, {"zone": zone_text(p, "easy")}, ["C1", "M18"] + (["S2"] if p.run_injury else []), list(notes)))
        elif k == "hy_upper":
            out.append(_make(p, "strength_upper", "upper_a", day, w, 0, 0, 0, deload, taper, False, notes, cyc))
        elif k == "hy_cross":
            minutes, det, nts, rules = HY.cross(_hctx(p, cyc, light, day, taper))
            out.append(Session(day, HB.KIND, HY.TITLES["hy_cross"] + (" (allégée)" if light else ""), minutes, det, rules, notes + nts))
        else:
            (minutes, det, nts, rules), got = built[k]
            out.append(Session(day, HB.KIND, HY.TITLES[got] + (" (allégée)" if light and got in ("hy_stations", "hy_comp") else ""), minutes, det, rules, notes + nts))
    return _enforce_caps(p, out)


def _week(p: Profile, monday: date, w: int, run_min: float, deload: bool, taper: bool, run_priority: bool, cyc: Cycle) -> list[Session]:
    if p.dedicated:
        return _week_dedicated(p, monday, w, run_min, deload, taper, cyc)
    run_min_in = run_min
    avail = [d for d in range(7) if d not in p.blocked]
    if len(avail) <= 1:
        return []
    n_days = min(p.days_per_week, len(avail) - 1)  # G5 : au moins un jour de repos
    placed: list[tuple[int, str, str]] = []  # (jour, type, variante)

    def on(d: int) -> list[str]:
        return [k for dd, k, _ in placed if dd == d]

    def feasible(d: int, kind: str, variant: str = "") -> bool:
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
        if kind == "strength_crossfit" and variant != "cf_gym" and any((k == "run_long" and _cd(d, dd) <= 1) or (k in KEY and dd == d) for dd, k, _ in placed):
            return False  # conditionnement intense : jamais la veille ou le lendemain de la sortie longue, ni le jour d'une séance clé
        if kind == "strength_crossfit" and variant in HARD_HY and any((k in KEY and _cd(d, dd) <= 1) or (v in HARD_HY and _cd(d, dd) <= 1) for dd, k, v in placed):
            return False  # I7, M14 : station ou course compromise = séance dure des jambes, 48 h de toute autre séance clé ou dure
        if kind == "run_long" and any(k == "strength_crossfit" and v != "cf_gym" and _cd(d, dd) <= 1 for dd, k, v in placed):
            return False
        if kind in KEY and any(k == "strength_crossfit" and v in HARD_HY and _cd(d, dd) <= 1 for dd, k, v in placed):
            return False
        if kind == "run_quality" and any(k == "strength_crossfit" and dd == d for dd, k, _ in placed):
            return False
        return True

    prefs = {"run_long": [5, 6, 0, 4], "run_quality": [1, 2, 3], "strength_lower": [2, 3, 1], "upper_a": [0, 1, 4], "upper_b": [2, 3, 4], "full": [1, 3, 5], "crossfit": [3, 2, 4, 1],
             "cf_gym": [1, 4, 5], "hy_stations": [3, 2, 4, 1], "hy_comp": [5, 4, 2, 1], "hy_sim": [5, 6, 4], "hy_half": [5, 6, 4]}

    def place(kind: str, variant: str = "", order: list[int] | None = None) -> bool:
        pref_days = (p.run_days if kind.startswith("run_") else p.strength_days)
        order = order or prefs.get(variant or kind, avail)
        used = {x[0] for x in placed}
        best = None
        for d in avail:
            if not feasible(d, kind, variant):
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

    hy_ev = bool(p.event and p.event.get("hyrox"))
    hy_early = p.after_break and w < 2
    hy_light = taper or run_priority or deload or hy_early
    hy: list[str] = []  # séances hybrides de la semaine (M9, I7)
    if p.hybrid == "crossfit":
        if not run_priority and not taper and not hy_early:  # M9 : la course l'emporte près de l'objectif
            hy = ["crossfit"] + (["cf_gym"] if (not p.strength and p.days_per_week >= 4) else [])
    elif p.hybrid == "hyrox" and not hy_early and (not taper or hy_ev):
        sim = _sim_week(p, cyc, run_min, taper)
        if run_priority or taper:  # entretien : une séance de stations légère, jamais de course compromise
            hy = ["hy_stations"]
        else:  # sortie longue + qualité + une séance hybride = les 3 jours durs que G5 permet : stations et course compromise alternent d'une semaine à l'autre
            hy = [HY_SIM[sim] if sim else ("hy_comp" if (cyc.week_in_block - 1) % 2 == 1 else "hy_stations")]
    hy_run = 0.0  # la course des séances hybrides compte dans le volume de course de la semaine (G1)
    if p.runs and hy:
        hctx = _hctx(p, cyc, hy_light, monday, taper)
        for v in hy:
            if v == "hy_comp":
                hy_run += HY.comp_run_min(hctx, HY.comp_reps(hctx, run_min))
            elif v in ("hy_sim", "hy_half"):
                hy_run += round((8 if v == "hy_sim" else 4) * hctx.pace)
        run_min = max(run_min - hy_run, 0.6 * run_min)
    for i, v in enumerate(hy):
        if i == 0 and "upper_b" in variants:
            variants[variants.index("upper_b")] = v
        elif i == 0 and "full" in variants:
            variants[variants.index("full")] = v
        else:
            variants.append(v)  # deux séances de musculation ou moins : le conditionnement s'ajoute
    quality_planned = False
    dropped: list[str] = []  # G9 : séance voulue mais sans jour compatible, signalée dans les notes de la semaine
    quality_ok = (p.runs and not deload and not taper and not p.run_injury and w >= 1 and run_min >= 120
                  and not (p.weeks_since_run is not None and p.weeks_since_run >= 4 and w < 3) and not (p.after_break and w < 3))
    if p.runs:
        if "hy_sim" not in hy and not place("run_long"):  # la simulation complète (8 km de course) tient lieu de sortie longue de la semaine (M21)
            dropped.append(DROPPED["run_long"])
        if quality_ok:
            quality_planned = place("run_quality")
            if not quality_planned:
                dropped.append(DROPPED["run_quality"])
    for v in variants:
        if v == "lower" and not place("strength_lower", "lower"):
            dropped.append(DROPPED["lower"])
        elif v == "upper_a" and not place("strength_upper", "upper_a"):
            dropped.append(DROPPED["upper"])
    for v in sorted(variants, key=lambda x: x not in ("hy_sim", "hy_half", "hy_comp")):  # la séance la plus dure est placée en premier
        if v in HY_VARIANTS:
            if not place("strength_crossfit", v):
                if v == "crossfit" and place("strength_upper", "upper_b"):  # aucun jour compatible : séance de musculation à la place
                    dropped.append(DROPPED["crossfit_replaced"])
                else:
                    dropped.append(DROPPED["hybrid"])
        elif v == "upper_b" and not place("strength_upper", "upper_b"):
            dropped.append(DROPPED["upper"])
        elif v == "full" and not place("strength_full", "full", prefs["full"]):
            dropped.append(DROPPED["full"])
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
    notes += _injury_notes(p) + list(dict.fromkeys(dropped))
    out = []
    for d, kind, variant in sorted(placed):
        out.append(_make(p, kind, variant, monday + timedelta(days=d), w, long_min, q_min, easy_min, deload, taper, run_priority, notes, cyc, run_min_in))
    return _enforce_caps(p, out)


def _make(p: Profile, kind: str, variant: str, day: date, w: int, long_min: int, q_min: int, easy_min: int, deload: bool, taper: bool,
          run_priority: bool, notes: list[str], cyc: Cycle, run_budget: float | None = None) -> Session:
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
    if kind == "strength_crossfit" and variant == "crossfit":
        minutes, det, cf_notes = CF.build(cyc, p.level, p.injuries)
        return Session(day, kind, "Séance CrossFit" + (" (allégée)" if cyc.deload else ""), minutes, det, ["M9", "G5"], list(notes) + cf_notes)
    if kind == "strength_crossfit":
        light = deload or taper or run_priority
        ctx = _hctx(p, cyc, light, day, taper)
        if variant == "cf_gym":
            minutes, det, hy_notes, rules = HB.build("cf_gym", ctx)
            return Session(day, kind, HB.TITLES["cf_gym"] + (" (allégée)" if light else ""), minutes, det, rules + ["I7"], list(notes) + hy_notes)
        (minutes, det, hy_notes, rules), got = HY.build_station_variant(variant, ctx, run_budget)
        return Session(day, kind, HY.TITLES[got] + (" (allégée)" if light and got in ("hy_stations", "hy_comp") else ""), minutes, det, rules + ["I7"], list(notes) + hy_notes)
    maint = run_priority or taper
    n_build = p.deload_cycle - 1
    slots = S.session_plan(variant, maint, build=min(cyc.week_in_block - 1, n_build - 1), n_build=n_build, deload=deload or taper, block=cyc.block_no)
    if run_priority and variant != "lower" and not (deload or taper):  # course proche : un peu moins d'accessoires
        for sl in slots:
            if sl["role"] == "accessory":
                sl["sets"] = str(max(2, int(sl["sets"]) - 1))
    title = S.TITLES[variant] + (" (entretien)" if maint and variant == "lower" else "")
    rules = ["M1" if not maint else "M2", "M3", "M5", "M7"] + (["M6"] if p.focus_upper else []) + (["I1", "I2"] if kind == "strength_lower" else [])
    cap = _cap(p, day) if p.caps_declared else None
    trimmed = False
    while cap and 35 + 6 * len(slots) > cap * CAP_TOLERANCE and len(slots) > 2:  # G6 (à 10 % près) : accessoires, puis gainage, puis mouvements au-delà des deux premiers
        by_role = {r: [i for i, sl in enumerate(slots) if sl["role"] == r] for r in ("accessory", "core")}
        order = by_role["accessory"] or by_role["core"] or list(range(2, len(slots)))
        slots.pop(order[-1])
        trimmed = True
    n = len(slots)
    sess_notes = list(notes)
    if trimmed:
        sess_notes.append("Séance raccourcie pour tenir dans votre durée maximale (G6) : les exercices d'appoint passent en premier.")
    if kind == "strength_lower":
        sess_notes.append("Priorité course : les jambes restent en entretien (force, pas d'épuisement)." if maint else
                          "Jambes une fois par semaine : force, loin des séances de course clés.")
    sess_notes.append("Progression : quand vous atteignez le haut de la fourchette sur toutes les séries, ajoutez 2,5 kg (haut du corps) ou 5 kg (jambes).")
    return Session(day, kind, title, 35 + 6 * n, {"variant": variant, "slots": slots}, rules, sess_notes)
