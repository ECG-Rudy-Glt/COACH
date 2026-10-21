"""Programmation hybride dédiée (règles M10, M14 à M17) : microcycle CrossFit de 3 à 6 séances et briques communes avec Hyrox.

Le moteur compose une semaine à partir de « créneaux » (force bas du corps, force haut du corps, gymnastique, metcon, aérobie, prévention).
Chaque créneau a une intensité (0 facile, 1 modérée, 2 dure) et des groupes musculaires ; le placement interdit deux jours durs d'affilée sur les mêmes
groupes (M14). Tout est déterministe : mêmes faits, même semaine. Les mouvements incompatibles avec une blessure déclarée sont remplacés (S2).
"""
from __future__ import annotations

from dataclasses import dataclass, field
from itertools import combinations, permutations
from typing import Any

from app.plan.crossfit import AVOID, SCALE
from app.plan.cycles import Cycle

LEVELS = ["débutant", "intermédiaire", "avancé", "expert"]
KIND = "strength_crossfit"


@dataclass(frozen=True)
class Slot:
    key: str
    load: int  # 0 facile, 1 modéré, 2 dur
    groups: frozenset[str]
    prefs: tuple[int, ...]  # jours préférés (0 = lundi)


def _g(*names: str) -> frozenset[str]:
    return frozenset(names)


SLOTS: dict[str, Slot] = {s.key: s for s in [
    Slot("cf_force_lower", 2, _g("lower"), (0, 3, 1)),
    Slot("cf_force_upper", 2, _g("upper"), (4, 3, 2)),
    Slot("cf_gym", 1, _g("upper", "core"), (1, 3, 5)),
    Slot("cf_metcon", 2, _g("lower", "upper"), (2, 4, 5)),
    Slot("cf_metcon2", 1, _g("lower", "upper"), (5, 4, 2)),
    Slot("cf_aerobic", 0, _g(), (5, 3, 6)),
    Slot("cf_prevent", 0, _g(), (6, 3, 5)),
    Slot("hy_run_q", 2, _g("lower"), (1, 2, 0)),
    Slot("hy_stations", 2, _g("lower", "upper"), (3, 2, 4)),
    Slot("hy_run_z2", 0, _g(), (5, 6, 3)),
    Slot("hy_run_z2b", 0, _g(), (1, 2, 0)),  # séance de qualité remplacée par un footing (volume, reprise, blessure)
    Slot("hy_comp", 2, _g("lower"), (5, 4, 6)),
    Slot("hy_upper", 1, _g("upper"), (0, 4, 2)),
    Slot("hy_cross", 0, _g(), (6, 3, 5)),
]}

CF_TEMPLATES = {2: ["cf_force_lower", "cf_metcon"],
                3: ["cf_force_lower", "cf_metcon", "cf_gym"],
                4: ["cf_force_lower", "cf_gym", "cf_metcon", "cf_aerobic"],
                5: ["cf_force_lower", "cf_gym", "cf_metcon", "cf_aerobic", "cf_force_upper"],
                6: ["cf_force_lower", "cf_gym", "cf_metcon", "cf_aerobic", "cf_force_upper", "cf_metcon2"]}


def cd(a: int, b: int) -> int:
    return min((a - b) % 7, (b - a) % 7)


def clash(a: Slot, b: Slot) -> bool:
    """M14 : deux séances dures qui se touchent sur les mêmes groupes."""
    return a.load >= 2 and b.load >= 2 and bool(a.groups & b.groups)


def assign(keys: list[str], avail: list[int], n_days: int, lighten: bool = False) -> tuple[dict[str, int], list[str]]:
    """Jour de chaque créneau (recherche exhaustive, ordre stable). Si aucune disposition ne respecte M14 et G5, le dernier créneau saute.

    Retourne (jour par créneau, créneaux conservés). `lighten` : semaine allégée, toutes les séances comptent pour modérées.
    """
    keys = list(keys)
    while keys:
        n = min(len(keys), n_days, len(avail))
        keys = keys[:n]
        best: tuple[int, tuple[int, ...], tuple[str, ...]] | None = None
        for days in combinations(avail, n):
            for perm in permutations(keys):
                cost, ok = 0, True
                for i, (d, k) in enumerate(zip(days, perm, strict=True)):
                    s = SLOTS[k]
                    cost += (s.prefs.index(d) if d in s.prefs else len(s.prefs) + 1)
                    for d2, k2 in zip(days[i + 1:], perm[i + 1:], strict=True):
                        if cd(d, d2) == 1:
                            s2 = SLOTS[k2]
                            if not lighten and clash(s, s2):
                                ok = False
                                break
                            cost += 3 * (s.load + s2.load >= 3)
                    if not ok:
                        break
                if ok and (best is None or cost < best[0]):
                    best = (cost, days, perm)
        if best:
            return dict(zip(best[2], best[1], strict=True)), list(keys)
        keys = keys[:-1]
    return {}, []


# ---- mouvements (nom, étiquettes de risque, remplacement sûr) -------------------------------------------------------------------------------------
MV: dict[str, tuple[str, frozenset[str], str]] = {
    "squat": ("Squat arrière", _g("knee"), "Hip thrust"),
    "fsquat": ("Squat avant", _g("knee"), "Hip thrust"),
    "dl": ("Soulevé de terre", _g("hinge"), "Hip thrust"),
    "rdl": ("Soulevé de terre roumain", _g("hinge"), "Hip thrust"),
    "spress": ("Développé militaire strict", _g("overhead"), "Développé incliné haltères"),
    "bench": ("Développé couché", _g(), "Développé couché"),
    "ppress": ("Push press", _g("overhead", "knee"), "Développé incliné haltères"),
    "bbrow": ("Rowing barre penché", _g("hinge"), "Rowing aux anneaux"),
    "clean": ("Épaulé technique", _g("hinge", "knee"), "Rowing haltère"),
    "snatch": ("Arraché technique", _g("overhead", "knee"), "Rowing haltère"),
}
# metcon : (nom, étiquettes, remplacement, unité) ; l'unité règle l'écriture « 12 cal de rameur »
MET: dict[str, tuple[str, frozenset[str], str, str]] = {
    "swing": ("swings kettlebell", _g("hinge"), "rameur", "rep"),
    "goblet": ("goblet squats", _g("knee"), "rameur", "rep"),
    "thruster": ("thrusters haltères", _g("overhead", "knee"), "rameur", "rep"),
    "pushup": ("pompes", _g(), "pompes", "rep"),
    "pullup": ("tractions", _g(), "rowing aux anneaux", "rep"),
    "burpee": ("burpees", _g("jump"), "sprawls sans saut", "rep"),
    "stepup": ("montées de banc", _g("knee"), "rameur", "rep"),
    "row": ("rameur", _g(), "rameur", "cal"),
    "bike": ("vélo assault bike", _g(), "vélo assault bike", "cal"),
    "ski": ("SkiErg", _g(), "SkiErg", "cal"),
    "rope": ("double unders", _g("jump"), "rameur", "rep"),
    "situp": ("relevés de buste", _g(), "relevés de buste", "rep"),
    "press": ("développés épaules haltères", _g("overhead"), "pompes déclive", "rep"),
    "wallball": ("wall balls", _g("overhead", "knee"), "rameur", "rep"),
    "carry": ("marche chargée (farmer)", _g(), "marche chargée (farmer)", "m"),
    "run": ("course", _g(), "rameur", "run"),
    "t2b": ("toes-to-bar", _g(), "relevés de genoux suspendus", "rep"),
    "dbsnatch": ("arrachés haltère", _g("overhead", "hinge"), "rameur", "rep"),
}
REGRESS = {"débutant": {"pullup": "rowing aux anneaux", "t2b": "relevés de genoux suspendus", "burpee": "sprawls sans saut", "thruster": "goblet squats"}}

CIRCUITS: list[list[tuple[str, int]]] = [
    [("swing", 15), ("pushup", 10), ("goblet", 12)],
    [("row", 12), ("thruster", 10), ("pullup", 6), ("situp", 15)],
    [("burpee", 8), ("wallball", 12), ("carry", 30), ("press", 10)],
    [("bike", 12), ("goblet", 10), ("pushup", 10), ("t2b", 6)],
    [("run", 200), ("stepup", 12), ("pullup", 8)],
    [("ski", 10), ("wallball", 15), ("burpee", 6)],
]
LADDERS = [["thruster", "pullup"], ["dbsnatch", "burpee"], ["swing", "t2b"]]


def avoid_tags(injuries: set[str]) -> set[str]:
    out: set[str] = set()
    for i in injuries:
        out |= AVOID.get(i, set())
    return out


@dataclass
class Ctx:
    """Tout ce qu'une séance hybride lit du profil et de la semaine."""
    cyc: Cycle
    level: str = "débutant"
    injuries: set[str] = field(default_factory=set)
    skills: set[str] = field(default_factory=set)
    zone: str = "allure de conversation"
    cap: int = 90
    light: bool = False  # semaine allégée, affûtage ou reprise
    run_injury: bool = False
    taper: bool = False  # affûtage ou semaine de l'objectif : séances très courtes
    pace: float = 5.7  # allure Hyrox (min/km)
    std: dict[str, int] = field(default_factory=dict)  # charges standard de la catégorie visée
    weak: set[str] = field(default_factory=set)
    has_gear: bool = True  # traîneau et SkiErg disponibles
    hr_max: int | None = None

    @property
    def bad(self) -> set[str]:
        return avoid_tags(self.injuries)

    @property
    def wib(self) -> int:
        return self.cyc.week_in_block - 1

    @property
    def blk(self) -> int:
        return self.cyc.block_no

    @property
    def scale(self) -> float:
        return SCALE.get(self.level, 1.0)


def block(title: str, minutes: int, items: list[str], effort: str | None = None, optional: bool = False) -> dict[str, Any]:
    b: dict[str, Any] = {"title": title, "minutes": minutes, "items": items, "optional": optional}
    if effort:
        b["effort"] = effort
    return b


def fit(blocks: list[dict[str, Any]], cap: int) -> tuple[int, list[dict[str, Any]]]:
    """G6 : respecte la durée maximale en retirant d'abord les blocs facultatifs (accessoires, prévention)."""
    blocks = list(blocks)
    while sum(b["minutes"] for b in blocks) > cap:
        opt = [i for i, b in enumerate(blocks) if b.get("optional")]
        if not opt:
            break
        blocks.pop(opt[-1])
    for title, floor in (("Échauffement", 6), ("Retour au calme", 3)):  # puis on raccourcit l'échauffement et le retour au calme avant de dépasser la durée permise
        extra = sum(b["minutes"] for b in blocks) - cap
        for b in blocks:
            if extra > 0 and b["title"] == title and b["minutes"] > floor:
                cut = min(extra, b["minutes"] - floor)
                b["minutes"] -= cut
                extra -= cut
    for b in blocks:
        b.pop("optional", None)
    return sum(b["minutes"] for b in blocks), blocks


def mv_name(key: str, bad: set[str]) -> str:
    name, tags, alt = MV[key]
    return alt if tags & bad else name


CARDIO = ("rameur", "SkiErg", "vélo assault bike")


def met_name(key: str, ctx: Ctx) -> tuple[str, str]:
    """(nom, unité) du mouvement : remplacé par sa variante si une blessure l'exige (S2), régressé pour un débutant (M16)."""
    name, tags, alt, unit = MET[key]
    if tags & ctx.bad or (key == "run" and ctx.run_injury):
        return alt, ("cal" if alt in CARDIO else "rep")
    reg = REGRESS.get(ctx.level, {}).get(key)
    if reg:
        return reg, ("cal" if reg in CARDIO else "rep")
    return name, unit


def met_text(key: str, n: int, ctx: Ctx) -> str:
    name, unit = met_name(key, ctx)
    base = MET[key][3]
    if base in ("m", "run"):
        n = 10 if unit == "cal" else round(n * ctx.scale / 5) * 5
    else:
        n = max(round(n * ctx.scale), 2)
    if unit == "cal":
        return f"{n} cal de {name}"
    if unit == "run":
        return f"{n} m de course"
    if unit == "m":
        return f"{n} m de {name}"
    return f"{n} {name}"


# ---- progression ---------------------------------------------------------------------------------------------------------------------------------
def lift_scheme(ctx: Ctx, heavy: bool = True) -> tuple[int, int, int]:
    """(séries, répétitions, répétitions en réserve) du mouvement principal (M8, M12) : jamais à l'échec."""
    wib, blk = ctx.wib, ctx.blk
    if ctx.light:
        return 3, 5, 4
    sets = min(3 + wib + (1 if blk >= 2 else 0), 6)
    reps = (5, 4, 3)[min(wib, 2)] if heavy else 8
    rir = (3, 2, 1)[min(wib, 2)] if heavy else 3 - min(wib, 1)
    if ctx.level == "débutant":
        sets, reps, rir = max(sets - 1, 3), max(reps, 5) if heavy else 8, min(rir + 1, 4)
    return sets, reps, rir


def _round5(x: float) -> int:
    return int(round(x / 5) * 5)


def warmup(minutes: int, extra: list[str] | None = None) -> dict[str, Any]:
    return block("Échauffement", minutes, ["3 min de rameur ou vélo facile", "Mobilité épaules, hanches et chevilles"] + (extra or []))


def cooldown() -> dict[str, Any]:
    return block("Retour au calme", 5, ["Marche, respiration, étirements doux des hanches et des épaules"])


def prevention(ctx: Ctx) -> dict[str, Any]:
    items = ["2 tours : rotation externe d'épaule à l'élastique 12, pont fessier sur une jambe 10 par côté, gainage latéral 30 s par côté"]
    if "épaule" in ctx.injuries:
        items.append("Épaule sensible : gardez les coudes sous la hauteur des épaules et restez sans douleur")
    if {"genou", "hanche"} & ctx.injuries:
        items.append("Genou ou hanche sensible : montées de banc basses et contrôlées, sans douleur")
    return block("Prévention", 6, items, optional=True)


def done(blocks: list[dict[str, Any]], ctx: Ctx, variant: str, notes: list[str], rules: list[str]) -> tuple[int, dict[str, Any], list[str], list[str]]:
    minutes, blocks = fit(blocks, ctx.cap)
    if ctx.bad:
        notes = notes + ["Certains mouvements sont remplacés par une variante à cause de vos blessures déclarées."]
    if ctx.light:
        notes = notes + ["Semaine allégée : on garde le mouvement, pas la fatigue."]
    return minutes, {"variant": variant, "blocks": blocks}, notes, rules


# ---- séances CrossFit ----------------------------------------------------------------------------------------------------------------------------
def force_lower(ctx: Ctx):
    sets, reps, rir = lift_scheme(ctx)
    main = mv_name("squat" if ctx.blk % 2 else "fsquat", ctx.bad)
    second = mv_name("dl" if ctx.blk % 2 else "rdl", ctx.bad)
    s2 = max(sets - 1, 3)
    blocks = [
        warmup(10, ["2 séries de montée progressive sur le premier mouvement"]),
        block("Force — mouvement principal", 20, [f"{main} : {sets} séries de {reps}, {rir} répétitions en réserve"], "repos 2 à 3 min, jamais à l'échec"),
        block("Force — chaîne postérieure", 12, [f"{second} : {s2} séries de {reps}, {rir} répétitions en réserve"], "repos 2 min"),
        block("Accessoires", 10, ["Fentes marchées : 3 séries de 10 par jambe" if "knee" not in ctx.bad else "Pont fessier sur une jambe : 3 séries de 10 par jambe",
                                  "Gainage : 3 séries de 30 s"], optional=True),
        prevention(ctx),
        cooldown(),
    ]
    notes = ["Séance dure sur les jambes : pas de séance dure sur les jambes la veille ni le lendemain (M14).",
             "Charge choisie pour garder les répétitions en réserve indiquées : la technique prime sur la charge."]
    return done(blocks, ctx, "cf_force_lower", notes, ["M10", "M14", "M16", "M12", "M8", "G5"])


def force_upper(ctx: Ctx):
    sets, reps, rir = lift_scheme(ctx)
    press = mv_name("spress" if ctx.blk % 2 else "bench", ctx.bad)
    pull = mv_name("bbrow", ctx.bad)
    oly = mv_name("clean" if (ctx.wib + ctx.blk) % 2 else "snatch", ctx.bad)
    oly_sets = 4 if ctx.light else min(5 + ctx.wib, 7)
    blocks = [
        warmup(10, ["2 tours : 10 tirages d'élastique, 8 pompes lentes"]),
        block("Haltérophilie technique allégée", 12, [f"{oly} : {oly_sets} séries de 2 à charge légère",
                                                      "Barre vide ou très légère si le mouvement n'est pas maîtrisé ; arrêtez dès que la technique se dégrade"],
              "6 sur 10 au plus, vitesse de barre rapide, aucune répétition ratée"),
        block("Force — poussée", 15, [f"{press} : {sets} séries de {reps}, {rir} répétitions en réserve"], "repos 2 à 3 min"),
        block("Force — tirage", 10, [f"{pull} : {max(sets - 1, 3)} séries de 8, {rir + 1 if rir < 4 else rir} répétitions en réserve"], "repos 90 s"),
        block("Accessoires", 8, ["Élévations latérales haltères : 3 séries de 12", "Oiseau buste penché : 3 séries de 15"], optional=True),
        prevention(ctx),
        cooldown(),
    ]
    notes = ["L'haltérophilie reste technique et légère : on cherche la qualité du geste, pas la charge (M16).",
             "Poussée et tirage sont équilibrés pour protéger les épaules."]
    return done(blocks, ctx, "cf_force_upper", notes, ["M10", "M14", "M16", "M12", "M8", "G5"])


def gym_levels(ctx: Ctx) -> list[str]:
    n = round({"débutant": 5, "intermédiaire": 6, "avancé": 8, "expert": 8}.get(ctx.level, 6) * (0.6 if ctx.light else 1.0))
    n += 0 if ctx.light else min(ctx.wib, 2) + min(ctx.blk - 1, 2)
    bad = ctx.bad
    lvl = ctx.level
    pull = "Rowing aux anneaux" if lvl == "débutant" else "Tractions strictes"
    push = "Pompes sur banc" if lvl == "débutant" else ("Pompes strictes" if "overhead" in bad or lvl == "intermédiaire" else "Pompes en équilibre contre le mur")
    if lvl == "débutant":
        core = "Relevés de genoux suspendus"
    elif lvl == "intermédiaire":
        core = "Relevés de genoux suspendus, puis toes-to-bar assistés"
    else:
        core = "Toes-to-bar"
    hold = "Planche sur les coudes" if lvl == "débutant" or "overhead" in bad else "Équilibre sur les mains contre le mur"
    out = [f"{pull} : 5 séries de {n}", f"{push} : 4 séries de {max(n - 1, 4)}", f"{core} : 4 séries de {max(n - 1, 4)}", f"{hold} : 4 séries de 20 s"]
    if lvl in ("avancé", "expert") and "muscle-up" in ctx.skills and not ctx.light:
        out.append("Muscle-up : 6 essais techniques de 1 à 2 répétitions, jamais en fatigue")
    return out


def gym(ctx: Ctx):
    items = gym_levels(ctx)
    blocks = [
        warmup(8, ["Poignets, épaules et omoplates : 2 tours de 10 suspensions actives"]),
        block("Gymnastique et force du haut du corps", 25, items, "qualité avant quantité : arrêtez une série 1 à 2 répétitions avant la perte de forme"),
        block("Finisseur", 8, ["EMOM 8 min : minute impaire 8 pompes, minute paire 10 relevés de buste"], "6 à 7 sur 10", optional=True),
        prevention(ctx),
        cooldown(),
    ]
    notes = ["Les versions strictes viennent avant les versions avec élan : changez de niveau seulement quand les séries sont propres.",
             "Chaque mouvement a une régression : prenez-la dès que la forme se dégrade."]
    return done(blocks, ctx, "cf_gym", notes, ["M10", "M16", "M8"])


FORMATS = ["amrap", "fortime", "emom", "interval"]


def metcon_items(ctx: Ctx, offset: int) -> list[str]:
    circ = CIRCUITS[(ctx.blk - 1 + 2 * ctx.wib + offset) % len(CIRCUITS)]
    return [met_text(k, r, ctx) for k, r in circ]


def metcon(ctx: Ctx, second: bool = False):
    offset = 3 if second else 0
    items = metcon_items(ctx, offset)
    wib, blk = ctx.wib, ctx.blk
    if ctx.light:
        fmt, minutes, effort = "AMRAP 8 min, allure confortable", 8, "6 sur 10 : vous pourriez parler entre les tours"
        text = [f"AMRAP 8 min — tours de : {' · '.join(items)}"]
    else:
        pool = ["interval", "emom"] if second else FORMATS
        fmt_key = pool[(wib + blk - 1 + offset) % len(pool)]
        long_wod = round(min(12 + 2 * (blk - 1), 18) * (0.75 if ctx.level == "débutant" else 1.0))
        if fmt_key == "amrap":
            fmt, minutes, effort = f"AMRAP {long_wod} min", long_wod, "7 sur 10, allure tenable sur toute la durée"
            text = [f"AMRAP {long_wod} min — tours de : {' · '.join(items)}"]
        elif fmt_key == "fortime":
            rounds = 3 + min(blk - 1, 2) + (1 if ctx.level in ("avancé", "expert") else 0)
            ladder = LADDERS[(blk - 1 + wib) % len(LADDERS)]
            if wib % 2 == 0:
                fmt, minutes = "For Time 21-15-9", 12
                text = ["21-15-9, le plus vite possible avec une bonne exécution :"] + [met_name(k, ctx)[0] for k in ladder]
            else:
                fmt, minutes = f"{rounds} tours chronométrés", 6 + rounds * 3
                text = [f"{rounds} tours, le plus vite possible avec une bonne exécution : {' · '.join(items)}"]
            effort = "8 sur 10 sur les derniers tours, jamais d'échec technique"
        elif fmt_key == "emom":
            emom = max(len(items) * (min(12 + 2 * (blk - 1), 18) // len(items)), len(items) * 3)
            fmt, minutes, effort = f"EMOM {emom} min", emom, "7 à 8 sur 10, 10 à 15 s de repos par minute"
            stations = " · ".join(f"minute {i + 1} : {it}" for i, it in enumerate(items))
            text = [f"EMOM {emom} min, en boucle — {stations}"]
        else:
            reps = 4 + min(blk - 1, 2) - (1 if ctx.level == "débutant" else 0)
            fmt, minutes, effort = f"{reps} × 3 min, repos 2 min", reps * 5 - 2, "8 sur 10 sur chaque effort, la même quantité de travail à chaque intervalle"
            text = [f"{reps} intervalles de 3 min : enchaînez {' · '.join(items)} sans vous arrêter, puis 2 min de repos"]
        if second:
            effort = "7 sur 10 : séance de capacité, jamais à fond"
    blocks = [warmup(8, ["2 tours : 8 pompes lentes, 10 balancements de jambe, 6 ponts fessiers", "Mouvements du metcon à vide, 1 minute"]),
              block(f"Metcon — {fmt}", minutes, text, effort), cooldown()]
    notes = ["Séance de conditionnement : intensité haute, loin de la sortie longue.",
             "Adaptez la charge ou prenez la variante plutôt que de sacrifier la technique ; notez votre score (tours ou temps) dans la remarque."]
    rules = ["M10", "M15"] + ([] if second else ["M14", "G5"])
    return done(blocks, ctx, "cf_metcon2" if second else "cf_metcon", notes, rules)


def zone2_text(ctx: Ctx) -> str:
    if ctx.hr_max:
        return f"{round(ctx.hr_max * 0.60)}-{round(ctx.hr_max * 0.75)} bpm, ou allure de conversation"
    return "allure de conversation, respiration nasale possible"


def aerobic(ctx: Ctx, cross: bool = False):
    mods = ["Rameur", "Vélo", "Course facile", "SkiErg"]
    if cross or ctx.run_injury or ctx.bad & {"jump"}:  # `cross` : aérobie sans impact (Hyrox), la course a ses propres séances
        mods.remove("Course facile")
    mod = mods[(ctx.wib + ctx.blk) % len(mods)]
    base = 30 * 1.08 ** (ctx.wib + 3 * (ctx.blk - 1)) * {"débutant": 0.85, "intermédiaire": 1.0}.get(ctx.level, 1.15)
    minutes = _round5(min(base, 60) * (0.65 if ctx.light else 1.0))
    blocks = [warmup(5), block("Capacité aérobie", minutes, [f"{mod} : {minutes} min en continu, zone 2 ({zone2_text(ctx)})", "Allure régulière, vous devez pouvoir parler en phrases complètes"],
                               "3 à 4 sur 10 : la séance doit laisser frais"), cooldown()]
    notes = ["La base aérobie soutient la récupération entre les efforts durs ; elle ne doit pas devenir une séance dure.",
             "La durée monte de 8 % par semaine au plus, puis redescend en semaine allégée (G1, G2)."]
    return done(blocks, ctx, "hy_cross" if cross else "cf_aerobic", notes, ["M18" if cross else "M10", "M17", "G1"])


def prevent_session(ctx: Ctx):
    items = ["3 tours : rotation externe d'épaule à l'élastique 12 par côté, tirage d'élastique en W 15, pont fessier sur une jambe 10 par côté, "
             "oiseau-chien 8 par côté, gainage latéral 30 s par côté",
             "Mobilité thoracique, hanches et chevilles : 6 min sans douleur"]
    if ctx.injuries:
        items.append("Zone sensible déclarée : gardez l'amplitude sans douleur et privilégiez les mouvements lents")
    blocks = [block("Accessoires et prévention", 30, items, "2 à 3 sur 10, rien ne doit être éprouvant"), cooldown()]
    return done(blocks, ctx, "cf_prevent", ["Séance de récupération active : elle prépare la suite de la semaine."], ["M10", "M16"])


BUILDERS = {"cf_force_lower": force_lower, "cf_force_upper": force_upper, "cf_gym": gym, "cf_metcon": metcon, "cf_aerobic": aerobic, "cf_prevent": prevent_session}


def build(key: str, ctx: Ctx):
    if key == "cf_metcon2":
        return metcon(ctx, second=True)
    return BUILDERS[key](ctx)


TITLES = {"cf_force_lower": "CrossFit — force, bas du corps", "cf_force_upper": "CrossFit — force haut du corps et haltérophilie technique",
          "cf_gym": "CrossFit — gymnastique et skill", "cf_metcon": "CrossFit — metcon", "cf_metcon2": "CrossFit — metcon de capacité",
          "cf_aerobic": "CrossFit — capacité aérobie", "cf_prevent": "CrossFit — accessoires et prévention"}


def crossfit_keys(n_days: int, light: bool, injuries: set[str]) -> list[str]:
    """Créneaux de la semaine (M10) : 2 à 6 séances. En semaine allégée ou avec blessure déclarée, le 2e metcon devient de la prévention."""
    keys = list(CF_TEMPLATES[max(2, min(6, n_days))])
    if "cf_metcon2" in keys and (light or injuries):
        keys[keys.index("cf_metcon2")] = "cf_prevent"
    return keys
