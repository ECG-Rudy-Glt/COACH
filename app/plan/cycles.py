"""Périodisation : position dans le bloc (3+1), phase du cycle vers l'objectif, continuité entre deux générations du plan.

La position est enregistrée dans chaque séance (`details.cycle`) : regénérer le plan reprend le cycle là où il en était
au lieu de repartir de zéro, et le coach IA lit la même information (règles G7, M8).
"""
from __future__ import annotations

from dataclasses import asdict, dataclass
from datetime import date, timedelta
from typing import Any

MAX_GAP_WEEKS = 8  # au-delà d'une pause aussi longue, un nouveau cycle démarre

MACRO = {
    "base": ("Base", "Construire la régularité et le volume, sans chercher la performance."),
    "build": ("Développement", "Le volume et l'intensité montent bloc après bloc vers l'objectif."),
    "peak": ("Pic de forme", "Les dernières semaines fortes avant l'affûtage : volume maximal, séances proches de l'objectif, aucun ajout de charge inutile."),
    "taper": ("Affûtage", "Le volume baisse, l'intensité est conservée : la fatigue part, la forme reste."),
    "race": ("Semaine de l'objectif", "Peu de volume, quelques rappels d'allure, repos et sommeil."),
}


def macro_phase(weeks_to_event: int | None) -> str:
    """Phase vers l'objectif daté (semaines pleines avant l'événement) ; sans objectif, la base se poursuit."""
    if weeks_to_event is None:
        return "base"
    if weeks_to_event <= 0:
        return "race"
    if weeks_to_event == 1:
        return "taper"
    if weeks_to_event <= 4:
        return "peak"
    return "build" if weeks_to_event <= 12 else "base"


@dataclass(frozen=True)
class Cycle:
    anchor: str  # lundi du premier bloc (ISO) : fixe la position pour toutes les générations suivantes
    block_no: int  # 1, 2, 3… : la surcharge se fait aussi d'un bloc à l'autre
    week_in_block: int  # 1..block_len
    block_len: int
    deload: bool
    macro: str
    weeks_to_event: int | None

    @property
    def label(self) -> str:
        week = f"Bloc {self.block_no} · semaine {self.week_in_block}/{self.block_len}"
        return week + (" (allégée)" if self.deload else "")

    def as_dict(self) -> dict[str, Any]:
        return {**asdict(self), "label": self.label, "macro_label": MACRO[self.macro][0], "macro_text": MACRO[self.macro][1]}


def cycle_for(monday: date, anchor: date, block_len: int, weeks_to_event: int | None) -> Cycle:
    idx = max(0, (monday - anchor).days // 7)
    wib = idx % block_len
    macro = macro_phase(weeks_to_event)
    deload = wib == block_len - 1 and macro not in ("taper", "race")  # l'affûtage remplace la semaine allégée
    return Cycle(anchor.isoformat(), idx // block_len + 1, wib + 1, block_len, deload, macro, weeks_to_event)


def _monday(d: date) -> date:
    return d - timedelta(days=d.weekday())


def continue_anchor(existing: list[dict[str, Any]], block_len: int, monday0: date) -> date | None:
    """Ancre du cycle à reprendre d'après les séances déjà planifiées ou faites (None : nouveau cycle).

    Les séances générées avant l'arrivée des cycles n'ont pas d'information : leur première semaine sert d'ancre.
    """
    rows = [r for r in existing if r["day"] < monday0 and (monday0 - r["day"]).days <= MAX_GAP_WEEKS * 7]
    if not rows:
        return None
    marked = [r for r in sorted(rows, key=lambda r: r["day"]) if (r.get("details") or {}).get("cycle")]
    if marked:
        cyc = marked[-1]["details"]["cycle"]
        if cyc.get("block_len") != block_len:
            return None
        return date.fromisoformat(cyc["anchor"])
    return _monday(min(r["day"] for r in rows))


def describe(sessions: list[dict[str, Any]], today: date) -> dict[str, Any] | None:
    """Position actuelle et projection des 8 prochaines semaines (pour l'écran et le coach IA).

    Le plan n'est généré qu'une semaine à la fois : le cycle futur est donc projeté depuis l'ancre enregistrée dans les séances,
    pas lu dans des semaines qui n'existent pas encore.
    """
    by_week: dict[date, dict[str, Any]] = {}
    for s in sessions:
        cyc = (s.get("details") or {}).get("cycle")
        if cyc:
            by_week.setdefault(_monday(s["day"]), cyc)
    if not by_week:
        return None
    this = _monday(today)
    ref_monday = max((m for m in by_week if m <= this), default=min(by_week))
    ref = by_week[ref_monday]
    anchor, length = date.fromisoformat(ref["anchor"]), ref["block_len"]
    wte = ref.get("weeks_to_event")

    def at(i: int) -> dict[str, Any]:
        monday = this + timedelta(weeks=i)
        w = None if wte is None else max(0, wte - (monday - ref_monday).days // 7)
        return cycle_for(monday, anchor, length, w).as_dict()

    weeks = [at(i) for i in range(8)]
    upcoming = [{"semaine": (this + timedelta(weeks=i)).isoformat(), "bloc": c["block_no"], "position": f'{c["week_in_block"]}/{c["block_len"]}',
                 "allegee": c["deload"], "phase": c["macro_label"]} for i, c in enumerate(weeks)]
    nxt = next((u["semaine"] for u in upcoming[1:] if u["allegee"]), None)
    return {"current": weeks[0], "upcoming": upcoming, "next_deload": nxt}
