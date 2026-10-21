"""Programmation Hyrox (règles M18 à M21) : 8 × 1 km de course + 8 stations, séances de stations, course compromise, simulations.

Les charges de course viennent du site officiel de l'organisateur (https://hyrox.com/the-fitness-race/, relevé le 21/10/2026) :
catégorie Open ou Pro, hommes ou femmes. L'entraînement n'atteint la charge de course que progressivement, selon le niveau (M19).
"""
from __future__ import annotations

from typing import Any

from app.plan import hybrid as H
from app.plan.cycles import Cycle
from app.plan.hybrid import Ctx, block, cooldown, done, prevention, warmup

SOURCE = "https://hyrox.com/the-fitness-race/"

# charges officielles (traîneau compris pour poussée et traction ; kettlebells : par main ; sac en kg ; médecine-ball en kg)
STANDARD: dict[tuple[str, str], dict[str, int]] = {
    ("open", "m"): {"sled_push": 152, "sled_pull": 103, "farmer": 24, "lunges": 20, "wallballs": 6},
    ("open", "f"): {"sled_push": 102, "sled_pull": 78, "farmer": 16, "lunges": 10, "wallballs": 4},
    ("pro", "m"): {"sled_push": 202, "sled_pull": 153, "farmer": 32, "lunges": 30, "wallballs": 9},
    ("pro", "f"): {"sled_push": 152, "sled_pull": 103, "farmer": 24, "lunges": 20, "wallballs": 6},
}
# nom, distance de course, unité, étiquettes de risque, station de remplacement
STATIONS: dict[str, tuple[str, int, str, frozenset[str], str]] = {
    "skierg": ("SkiErg", 1000, "m", H._g(), "skierg"),
    "sled_push": ("Poussée de traîneau", 50, "m", H._g("knee"), "skierg"),
    "sled_pull": ("Traction de traîneau", 50, "m", H._g("hinge"), "skierg"),
    "bbj": ("Burpee broad jumps", 80, "m", H._g("jump", "knee"), "row"),
    "row": ("Rameur", 1000, "m", H._g(), "row"),
    "farmer": ("Farmers carry", 200, "m", H._g(), "farmer"),
    "lunges": ("Fentes avec sac de sable", 100, "m", H._g("knee"), "farmer"),
    "wallballs": ("Wall balls", 100, "rép", H._g("overhead", "knee"), "row"),
}
ORDER = list(STATIONS)
STEP = {"sled_push": 5, "sled_pull": 5, "farmer": 2, "lunges": 2, "wallballs": 1}
LEVEL_F = {"débutant": 0.60, "intermédiaire": 0.80, "avancé": 0.95, "expert": 1.0}
STATIONS_MIN = {"débutant": 42, "intermédiaire": 36, "avancé": 32, "expert": 28}  # durée des 8 stations d'une simulation complète (ordre de grandeur)
WEAK_LABELS = {"SkiErg": "skierg", "sled push": "sled_push", "sled pull": "sled_pull", "burpee broad jumps": "bbj", "rameur": "row", "farmers carry": "farmer",
               "sandbag lunges": "lunges", "wall balls": "wallballs"}
HY_TEMPLATES = {2: ["hy_stations", "hy_run_q"],
                3: ["hy_run_q", "hy_stations", "hy_run_z2"],
                4: ["hy_run_q", "hy_stations", "hy_run_z2", "hy_comp"],
                5: ["hy_run_q", "hy_stations", "hy_run_z2", "hy_comp", "hy_upper"],
                6: ["hy_run_q", "hy_stations", "hy_run_z2", "hy_comp", "hy_upper", "hy_cross"]}
TITLES = {"hy_stations": "Hyrox — stations", "hy_comp": "Hyrox — course compromise", "hy_half": "Hyrox — demi-simulation", "hy_sim": "Hyrox — simulation complète",
          "hy_cross": "Hyrox — aérobie sans impact"}


def standard_for(category: str | None, sex: str | None) -> dict[str, int]:
    """Charges de la catégorie visée : Pro si déclaré, sinon Open ; Doubles et Relais suivent Open."""
    return STANDARD[("pro" if (category or "").lower() == "pro" else "open", "f" if sex == "femme" else "m")]


def weak_keys(labels: Any) -> set[str]:
    return {WEAK_LABELS[x] for x in (labels or []) if x in WEAK_LABELS}


def hy_keys(n_days: int) -> list[str]:
    return list(HY_TEMPLATES[max(2, min(6, n_days))])


def pace_text(pace: float) -> str:
    return f"{int(pace)}:{round(pace % 1 * 60) % 60:02d}/km"


def load_kg(ctx: Ctx, key: str, factor: float = 1.0) -> int:
    """Charge d'entraînement d'une station : part de la charge de course selon le niveau, la position dans le bloc, jamais au-dessus du standard (M19)."""
    std = ctx.std[key]
    f = min(LEVEL_F.get(ctx.level, 0.6) + 0.05 * (ctx.blk - 1), 1.0)
    ramp = 0.75 if ctx.light else (0.90, 0.95, 1.0)[min(ctx.wib, 2)]
    step = STEP[key]
    return min(max(step, round(std * f * ramp * factor / step) * step), std)


def station_text(key: str, ctx: Ctx, frac: float, factor: float = 1.0) -> str:
    """Une station à `frac` de la distance de course ; remplacée si une blessure ou le manque de matériel l'exige."""
    name, dist, unit, tags, alt = STATIONS[key]
    gear = key not in ("skierg", "sled_push", "sled_pull") or ctx.has_gear
    if tags & ctx.bad or not gear:
        if key == "sled_push" and not ctx.has_gear and not tags & ctx.bad:
            return f"Fentes marchées lestées : {round(dist * frac)} m, charge modérée"
        if alt == key:
            alt = "row"
        key = alt
        name, dist, unit, tags, alt = STATIONS[key]
    q = round(dist * frac)
    if key == "wallballs":
        return f"{name} : {q} répétitions, {load_kg(ctx, key, factor)} kg"
    if key in ("sled_push", "sled_pull"):
        return f"{name} : {q} m, {load_kg(ctx, key, factor)} kg (traîneau compris)"
    if key == "farmer":
        return f"{name} : {q} m, 2 × {load_kg(ctx, key, factor)} kg"
    if key == "lunges":
        return f"{name} : {q} m, {load_kg(ctx, key, factor)} kg"
    return f"{name} : {q} m"


def _ordered(ctx: Ctx, keys: list[str]) -> list[str]:
    return sorted(keys, key=lambda k: k not in ctx.weak)  # stations faibles d'abord (tri stable)


def stations(ctx: Ctx):
    half = (ctx.blk + ctx.wib) % 2
    keys = _ordered(ctx, ORDER[:4] if half == 0 else ORDER[4:])
    tours = 1 if ctx.taper else 2 if (ctx.light or ctx.level == "débutant") else 2 + min(ctx.wib, 1) + (1 if ctx.blk >= 3 else 0)
    extra = " · ".join(STATIONS[k][0] for k in keys if k in ctx.weak)
    items = [f"{tours} tours, enchaînez les 4 stations (la moitié de la distance de course), repos 2 min entre les tours"] + [station_text(k, ctx, 0.5) for k in keys]
    if extra:
        items.append(f"Stations que vous jugez faibles, travaillées en premier : {extra}")
    minutes = tours * 9 + (tours - 1) * 2
    blocks = [warmup(10, ["5 min de SkiErg ou de rameur progressif", "1 série à vide de chaque station"]),
              block("Stations Hyrox — force-endurance", minutes, items, "7 à 8 sur 10, technique propre : on s'arrête avant de la perdre"),
              block("Accessoires", 8, ["Suspension à la barre : 3 séries de 30 s (prise pour les farmers)", "Gainage : 3 séries de 30 s"], optional=True),
              prevention(ctx), cooldown()]
    notes = ["Les charges restent sous celles de la course et montent de bloc en bloc jusqu'au standard de votre catégorie (M19).",
             "Séance dure pour les jambes : elle n'est pas collée à la course compromise ni à la séance de qualité (M14)."]
    return done(blocks, ctx, "hy_stations", notes, ["M18", "M19", "M14", "G5"])


def comp_reps(ctx: Ctx, run_budget: float | None = None) -> int:
    n = (3, 4, 5)[min(ctx.wib, 2)] + min(ctx.blk - 1, 2)
    if ctx.level == "débutant":
        n -= 1
    if ctx.light:
        n = 2 if ctx.taper else 3
    n = min(n, 8)
    if run_budget is not None and not ctx.run_injury:  # G1 : la course des séances hybrides compte dans le volume de course
        while n > 2 and n * ctx.pace > 0.4 * run_budget:
            n -= 1
    return n


def comp_run_min(ctx: Ctx, n: int) -> int:
    return 0 if ctx.run_injury else round(n * ctx.pace)


def comp(ctx: Ctx, run_budget: float | None = None):
    n = comp_reps(ctx, run_budget)
    start = (ctx.blk - 1 + 2 * ctx.wib) % len(ORDER)
    keys = _ordered(ctx, [ORDER[(start + i) % len(ORDER)] for i in range(len(ORDER))])[:n]
    if ctx.run_injury:
        run = "1 km de rameur ou de vélo à allure soutenue (sans impact)"
        head = "Zone qui porte la course sensible : la course est remplacée par du rameur ou du vélo (S2)"
    else:
        run = "1 km de course"
        head = f"Course à l'allure Hyrox ≈ {pace_text(ctx.pace)}, première répétition 10 s/km plus lente"
    items = [head] + [f"{i + 1}. {station_text(k, ctx, 0.5, 0.85)}, puis {run}" for i, k in enumerate(keys)]
    items.append("Repos : le temps de changer de station, 30 s au plus")
    minutes = round(n * (ctx.pace + 3.5))
    blocks = [warmup(12, ["5 min de footing facile", "3 accélérations de 20 s"]),
              block(f"Course compromise — {n} répétitions", minutes, items, "7 sur 10 : la course suit la station ; si les jambes lâchent, ralentissez sans vous arrêter"),
              prevention(ctx), cooldown()]
    notes = ["La course qui suit un effort de station se travaille à part : jambes lourdes, respiration haute (course « compromise »).",
             "La course de cette séance compte dans votre volume de course de la semaine (G1)."]
    m, details, notes, rules = done(blocks, ctx, "hy_comp", notes, ["M18", "M20", "M14", "G5"])
    details["run_min"] = comp_run_min(ctx, n)
    return m, details, notes, rules


def sim(ctx: Ctx, full: bool):
    """Simulation : 8 (complète) ou 4 (demi) enchaînements 1 km de course + station. None si elle dépasse la durée maximale de l'utilisateur (G6)."""
    n = 8 if full else 4
    pairs = [f"{i + 1}. 1 km de course, puis {station_text(k, ctx, 1.0)}" for i, k in enumerate(ORDER[:n])] if not ctx.run_injury else \
            [f"{i + 1}. 1 km de rameur ou de vélo, puis {station_text(k, ctx, 1.0)}" for i, k in enumerate(ORDER[:n])]
    st = STATIONS_MIN.get(ctx.level, 42) * n // 8
    est = round(n * ctx.pace + st)
    minutes = 12 + est + 5
    if minutes > ctx.cap:
        return None
    head = [f"Allure visée ≈ {pace_text(ctx.pace)} sur chaque kilomètre, départ 10 s/km plus lent : la vitesse de course baisse au fil de la course, partez sous contrôle",
            f"Durée estimée : environ {est} min"]
    blocks = [warmup(12, ["5 min de footing facile", "3 accélérations de 20 s"]),
              block("Simulation complète" if full else "Demi-simulation", est, head + pairs, "8 sur 10, allure régulière : c'est la répétition de la course"),
              cooldown()]
    notes = ["Comme en course : aucune pause en dehors du changement de station ; notez vos temps de course et de station pour repérer votre point faible.",
             "Une seule simulation complète par préparation : elle sert de repère, pas d'entraînement quotidien (M21)."]
    m, details, notes, rules = done(blocks, ctx, "hy_sim" if full else "hy_half", notes, ["M18", "M21", "M20", "G5"])
    details["run_min"] = 0 if ctx.run_injury else round(n * ctx.pace)
    return m, details, notes, rules


def cross(ctx: Ctx):
    return H.aerobic(ctx, cross=True)


def sim_plan(cyc: Cycle, hyrox_event: bool, dated: bool) -> str | None:
    """Simulation de la semaine (M21) : complète 3 semaines avant l'objectif (4 si la décharge tombe là), demi-simulation 2 semaines plus tôt.

    Sans objectif daté : une demi-simulation à la 3e semaine d'un bloc sur deux, comme repère."""
    wte = cyc.weeks_to_event
    if dated and hyrox_event and wte is not None:
        def deload_at(k: int) -> bool:
            return (cyc.week_in_block - 1 + wte - k) % cyc.block_len == cyc.block_len - 1

        full_wk = 4 if deload_at(3) else 3
        if wte == full_wk:
            return "full"
        if wte == full_wk + 2 and not deload_at(full_wk + 2):
            return "half"
        return None
    if not dated and cyc.block_no % 2 == 0 and cyc.week_in_block == 3 and not cyc.deload:
        return "half"
    return None


def quality_format(ctx: Ctx, q_min: int) -> str:
    """Séance de qualité de course (intervalles à l'allure Hyrox, seuil) dimensionnée sur le temps disponible."""
    usable = q_min - 15
    if usable < 8:
        return "6 × 1 min soutenu, 1 min de trot"
    if ctx.wib % 3 == 1:
        return f"{max(2, min(4, int(usable // 10)))} × 8 min au seuil, 2 min de trot"
    n = max(2, min(8, int(usable // (ctx.pace + 1.5))))
    return f"{n} × 1 km à allure Hyrox ({pace_text(ctx.pace)}), 90 s de trot entre les répétitions"


def build_station_variant(variant: str, ctx: Ctx, run_budget: float | None = None) -> tuple[Any, str]:
    """(résultat du constructeur, variante effectivement construite). Une simulation trop longue devient une demi-simulation, puis une course compromise."""
    if variant == "hy_sim":
        r = sim(ctx, True)
        if r:
            return r, "hy_sim"
        variant = "hy_half"
    if variant == "hy_half":
        r = sim(ctx, False)
        if r:
            return r, "hy_half"
        variant = "hy_comp"
    if variant == "hy_comp":
        return comp(ctx, run_budget), "hy_comp"
    return stations(ctx), "hy_stations"
