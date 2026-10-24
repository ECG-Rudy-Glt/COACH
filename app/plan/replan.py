"""Replanification de la fin de semaine (G13 à G17) : déterministe, sans LLM.

Le moteur ne crée aucune séance : il réorganise les séances que le plan de la semaine contient déjà (manquées ou restantes) sur les jours qui restent,
sans quitter les bornes du plan (phase, volume visé, nombre de séances par type), et retire ce qui ne tient pas en le disant plutôt que de tout caser.
Il réutilise les briques du moteur : séances clés (KEY), durées maximales (G6, G12), autour de l'événement (C6), gel de la course sur blessure (S2).
"""
from datetime import date, timedelta
from typing import Any

from app.plan import hybrid as HB
from app.plan.engine import HARD_HY, KEY, MIN_SESSION_MIN, Profile, _monday

VOLUME_FLOOR = 0.85  # G14 : en dessous de 85 % du volume de course visé, les footings restants sont allongés (convention de pratique)
STRETCH = 1.20  # G14 : un footing gagne 20 % au plus
MIN_REST_DAYS = 1  # G16
RUN_PREFIX = "run_"

# Sources par règle : identifiants de data/evidence/ (jamais inventés) ; « convention » = valeur de pratique sans publication qui la fixe.
SOURCES: dict[str, dict[str, Any]] = {
    "G13": {"ids": [], "convention": True},
    "G14": {"ids": ["RUN-005", "RUN-006", "RUN-007"], "convention": True},
    "G15": {"ids": ["HYB-001", "HYB-002"], "convention": True},
    "G16": {"ids": [], "convention": True},
    "G17": {"ids": [], "convention": True},
}

TEXT = {
    "G13": "Seules les séances prévues pour cette semaine sont replacées : aucune n'est ajoutée, une séance manquée n'est jamais doublée, la phase et le volume du plan ne changent pas.",
    "G14": "Le volume de course de la semaine (fait + à venir) ne dépasse pas celui prévu, donc la hausse reste dans le plafond de la semaine (G1).",
    "G15": "Pas de séance dure la veille ou le lendemain d'une autre, ni deux le même jour (G5, I1, I2, M14).",
    "G16": "Un jour de repos complet est gardé dans la semaine (G5).",
    "G17": "Trop peu de jours restants : le moteur retire les séances les moins prioritaires plutôt que de tout caser, et le dit (G9).",
}


def is_hard(r: dict[str, Any]) -> bool:
    return r["kind"] in KEY or (r["kind"] == HB.KIND and (r.get("details") or {}).get("variant") in HARD_HY)


def priority(r: dict[str, Any]) -> int:
    """Ordre de conservation (G9) : sortie longue, qualité, jambes ou conditionnement dur, footing, reste."""
    k = r["kind"]
    if k == "run_long":
        return 0
    if k == "run_quality":
        return 1
    if is_hard(r):
        return 2
    return 3 if k == "run_easy" else 4


def _light(r: dict[str, Any]) -> bool:
    return r["kind"] == "run_easy" or r["kind"] in ("strength_upper", "strength_full")


def _event_blocks(p: Profile, kind: str, day: date) -> bool:
    if not p.event:
        return False
    delta = (p.event["date"] - day).days
    hyrox = bool(p.event.get("hyrox"))
    if delta == 0:
        return True
    if -2 <= delta < 0 and (kind.startswith(RUN_PREFIX) or (hyrox and kind in (HB.KIND, "strength_lower"))):
        return True
    return delta == 1 and (kind == "strength_lower" or (hyrox and kind == HB.KIND))


def _logged_min(r: dict[str, Any]) -> float:
    return float((r.get("logged") or {}).get("minutes") or r["duration_min"])


def replan_rest_of_week(p: Profile, rows: list[dict[str, Any]], activities: list[dict[str, Any]], today: date, avoid_days: set[date] | None = None,
                        include_today: bool = False) -> dict[str, Any]:
    """Nouvelle fin de semaine d'après ce qui est déjà fait. `rows` : séances du plan (veille de la semaine à lundi suivant), `activities` : activités non reliées de la semaine."""
    avoid = avoid_days or set()
    monday = _monday(today)
    sunday = monday + timedelta(days=6)
    first = today if include_today else today + timedelta(days=1)
    week = [r for r in rows if monday <= r["day"] <= sunday]
    context = [r for r in rows if not monday <= r["day"] <= sunday and r["status"] != "skipped"]  # voisins hors semaine : l'espacement des séances dures les compte
    done = [r for r in week if r["status"] == "done"]
    pool = [r for r in week if r["status"] == "planned" and not (r.get("details") or {}).get("manual")]
    applied: dict[str, str] = {}
    notes: list[str] = []
    out: dict[str, Any] = {"week": monday.isoformat(), "from": first.isoformat(), "changes": [], "days": [], "applied": [], "notes": notes, "volume": None, "empty": False}
    if not pool or first > sunday:
        out["empty"] = True
        notes.append("Rien à replanifier : plus de séance prévue ou plus de jour restant cette semaine.")
        return out

    # jours occupés par ce qui est déjà fait (séances et activités non reliées) : (jour -> séances), pour l'espacement et le repos
    busy: dict[date, list[dict[str, Any]]] = {}
    for r in done + context:
        busy.setdefault(r["day"], []).append(r)
    act_days = {a["day"] for a in activities if monday <= a["day"] <= sunday}
    free = [first + timedelta(days=i) for i in range((sunday - first).days + 1) if (first + timedelta(days=i)).weekday() not in p.blocked]
    placed: dict[int, tuple[date, int]] = {}  # id -> (jour, durée)
    by_day: dict[date, list[dict[str, Any]]] = {}

    def neighbours_hard(day: date) -> bool:
        near = [x for d in (day - timedelta(days=1), day, day + timedelta(days=1)) for x in busy.get(d, []) + by_day.get(d, [])]
        return any(is_hard(x) for x in near)

    def cap_of(day: date) -> int:
        return p.weekend_max if day.weekday() >= 5 else p.weekday_max

    def fit(r: dict[str, Any], day: date) -> tuple[float, int] | None:
        """(coût, durée) du placement de r ce jour-là, ou None s'il enfreint G6, G15 ou C6."""
        if day not in free or _event_blocks(p, r["kind"], day):
            return None
        outdoor = r["kind"].startswith(RUN_PREFIX)
        if outdoor and day in avoid:
            return None
        dur, cost = r["duration_min"], 0.0
        if outdoor and dur > cap_of(day):
            dur, cost = cap_of(day), 0.5  # G12 : la course est plafonnée à la durée du jour
            if dur < MIN_SESSION_MIN:
                return None
        elif not outdoor and dur > cap_of(day) * 1.1:
            return None
        if is_hard(r) and neighbours_hard(day):
            return None
        same = busy.get(day, []) + by_day.get(day, [])
        if same:
            pair = {r["kind"] == "run_easy", same[0]["kind"] == "run_easy"}
            if len(same) >= 2 or not (_light(r) and _light(same[0])) or pair != {True, False}:
                return None  # deux séances le même jour : seulement un footing avec du haut du corps (I3)
            cost += 1.5
        return cost, dur

    order = sorted(pool, key=lambda r: (priority(r), r["day"], r["id"]))
    dropped: list[dict[str, Any]] = []
    for r in order:
        missed = r["day"] < first
        best: tuple[float, date, int] | None = None
        for d in free:
            f = fit(r, d)
            if f is None:
                continue
            gap = (d - first).days if missed else abs((d - r["day"]).days)
            c = (f[0] + gap, d, f[1])
            if best is None or c[:2] < best[:2]:
                best = c
        if best is None:
            dropped.append(r)
            continue
        placed[r["id"]] = (best[1], best[2])
        by_day.setdefault(best[1], []).append(r)

    # G16 : un jour sans aucune séance dans la semaine
    def occupied() -> set[date]:
        return {d for d in [*busy, *by_day, *act_days] if monday <= d <= sunday}

    while len(occupied()) > 7 - MIN_REST_DAYS:
        movable = sorted((r for r in pool if r["id"] in placed), key=lambda r: (-priority(r), -placed[r["id"]][0].toordinal()))
        if not movable:
            break
        r = movable[0]
        by_day[placed[r["id"]][0]].remove(r)
        del placed[r["id"]]
        dropped.append(r)
        applied["G16"] = TEXT["G16"]

    # G14 : volume de course. Cible = durées des courses prévues de la semaine ; fait = séances faites + activités de course non reliées
    target = float(sum(r["duration_min"] for r in week if r["kind"].startswith(RUN_PREFIX) and not (r.get("details") or {}).get("manual")))
    done_run = float(sum(_logged_min(r) for r in done if r["kind"].startswith(RUN_PREFIX)) + sum(a["minutes"] for a in activities if a.get("run")))
    easy = sorted((r for r in pool if r["id"] in placed and r["kind"] == "run_easy"), key=lambda r: placed[r["id"]][0])

    def run_total() -> float:
        return done_run + sum(placed[r["id"]][1] for r in pool if r["id"] in placed and r["kind"].startswith(RUN_PREFIX))

    if target and run_total() > target:  # le fait dépasse déjà le prévu : les footings à venir cèdent d'abord, jamais sous 20 min
        for r in reversed(easy):
            excess = run_total() - target
            if excess <= 0:
                break
            day, dur = placed[r["id"]]
            placed[r["id"]] = (day, max(MIN_SESSION_MIN, dur - round(excess)))
        applied["G14"] = TEXT["G14"]
    elif target and run_total() < VOLUME_FLOOR * target and not p.run_injury:
        for r in easy:
            gap = target - run_total()
            if gap <= 0:
                break
            day, dur = placed[r["id"]]
            new = min(round(dur * STRETCH / 5) * 5, cap_of(day), dur + round(gap))
            if new > dur:
                placed[r["id"]] = (day, new)
        applied["G14"] = TEXT["G14"]
    lost = None
    if target:
        total = run_total()
        lost = round(max(0.0, 1 - total / target) * 100)
        out["volume"] = {"target_min": round(target), "done_min": round(done_run), "planned_min": round(total - done_run), "lost_pct": lost}
        if lost > round((1 - VOLUME_FLOOR) * 100):
            applied["G14"] = TEXT["G14"]
            notes.append(f"Volume de course de la semaine réduit d'environ {lost} % par rapport au plan : le rattraper en entier demanderait d'entasser des séances (G14).")

    # changements, jour par jour
    for r in sorted(pool, key=lambda r: (r["day"], r["id"])):
        missed = r["day"] < first
        if r["id"] in placed:
            day, dur = placed[r["id"]]
            action = "keep" if day == r["day"] and dur == r["duration_min"] else "move" if day != r["day"] else "adjust"
            out["changes"].append({"session_id": r["id"], "title": r["title"], "kind": r["kind"], "from": r["day"].isoformat(), "to": day.isoformat(),
                                   "duration_from": r["duration_min"], "duration_to": dur, "action": action, "missed": missed})
        else:
            out["changes"].append({"session_id": r["id"], "title": r["title"], "kind": r["kind"], "from": r["day"].isoformat(), "to": None,
                                   "duration_from": r["duration_min"], "duration_to": None, "action": "drop", "missed": missed})
            applied["G17"] = TEXT["G17"]
            notes.append(f"« {r['title']} » est retirée de cette semaine : aucun jour restant ne la place sans entasser les séances dures ni enfreindre vos limites (G15, G17).")
    if any(c["action"] in ("move", "adjust") or c["action"] == "drop" for c in out["changes"]) or dropped:
        applied["G13"] = TEXT["G13"]
    hard_kept = [c for c in out["changes"] if c["to"] and c["action"] == "move" and c["kind"] in KEY]
    if hard_kept or any(c["action"] == "drop" and c["kind"] in KEY for c in out["changes"]):
        applied["G15"] = TEXT["G15"]
    if avoid:
        applied["W7"] = "Jours à météo déconseillée évités pour la course en extérieur (W1 à W6)."
    # le plan du jour : une ligne par jour restant
    for i in range((sunday - first).days + 1):
        d = first + timedelta(days=i)
        items = [{"session_id": r["id"], "title": r["title"], "kind": r["kind"], "duration_min": placed[r["id"]][1]} for r in sorted(by_day.get(d, []), key=lambda r: r["id"])]
        out["days"].append({"day": d.isoformat(), "blocked": d.weekday() in p.blocked, "sessions": items})
    out["applied"] = [{"rule": k, "text": v, **({"ids": SOURCES[k]["ids"], "convention": SOURCES[k]["convention"]} if k in SOURCES else {"ids": [], "convention": False})}
                      for k, v in sorted(applied.items())]
    return out
