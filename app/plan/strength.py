"""Séances de musculation : structure fondée sur des bonnes pratiques (docs/rules.md M1 à M7) et choix d'exercices de référence.

Principes :
- chaque groupe musculaire du haut du corps est travaillé 2 fois par semaine (haut A et haut B) quand 3 séances sont possibles ;
- les mouvements polyarticulaires viennent en premier, les isolations ensuite, le gainage en fin de séance ;
- tirages et poussées sont équilibrés (au moins autant de tirage que de poussée, épaules protégées par le travail des deltoïdes arrière) ;
- les jambes restent en entretien pour ne pas gêner la course (une séance, force plutôt qu'épuisement) ;
- les exercices sont choisis dans une liste ordonnée de mouvements de référence, avec repli selon le matériel et les blessures.
"""
from dataclasses import dataclass
from typing import Any

from app.repo import Repo

# mouvement -> (muscle principal, consigne d'exécution)
PATTERNS: dict[str, tuple[str, str]] = {
    "h_press": ("chest", "Omoplates serrées, pieds ancrés, descente contrôlée (2 s), poussez sans verrouiller brutalement."),
    "incline_press": ("chest", "Banc incliné à 30 degrés environ, coudes à 45 degrés du buste, amplitude complète."),
    "v_press": ("shoulders", "Gainez le tronc et les fessiers, poussez la charge au-dessus de la tête sans cambrer le bas du dos."),
    "v_pull": ("lats", "Initiez le mouvement par les omoplates, tirez les coudes vers les hanches, descente lente."),
    "h_pull": ("middle back", "Buste stable, tirez les coudes en arrière, serrez les omoplates en fin de mouvement."),
    "lateral": ("shoulders", "Légère inclinaison avant, montez les coudes jusqu'à l'horizontale, descente contrôlée."),
    "rear_delt": ("shoulders", "Buste penché, coudes légèrement fléchis, écartez en pensant à ouvrir les omoplates."),
    "triceps": ("triceps", "Coudes immobiles le long du corps, extension complète, retour lent."),
    "biceps": ("biceps", "Coudes fixes, pas d'élan, contrôlez la descente."),
    "squat": ("quadriceps", "Pieds ancrés, genoux dans l'axe des pieds, descendez en gardant le buste gainé, poussez dans le sol."),
    "hinge": ("hamstrings", "Dos neutre, hanches vers l'arrière, jambes presque tendues, ressentez l'étirement des ischio-jambiers."),
    "single_leg": ("glutes", "Buste droit, genou avant dans l'axe, poussée dans le talon, contrôle à la descente."),
    "calves": ("calves", "Amplitude complète, pause d'une seconde en bas et en haut."),
    "core": ("abdominals", "Respiration régulière, bas du dos stable, qualité avant durée."),
}

# Pour chaque mouvement : exercices de référence par ordre de préférence, avec le matériel exigé.
# `load` indique l'exercice de référence du record correspondant (charge de départ calculable).
CANDIDATES: dict[str, list[dict[str, Any]]] = {
    "h_press": [{"n": "Bench Press", "eq": ["barbell", "bench"], "load": "bench"}, {"n": "Dumbbell Bench Press", "eq": ["dumbbell", "bench"]},
                {"n": "Machine Bench Press", "eq": ["machine"]}, {"n": "Push-Up", "eq": []}, {"n": "Pushups", "eq": []}],
    "incline_press": [{"n": "Incline Dumbbell Press", "eq": ["dumbbell", "bench"]}, {"n": "Barbell Incline Bench Press - Medium Grip", "eq": ["barbell", "bench"]},
                      {"n": "Incline Push-Up", "eq": []}, {"n": "Push-Up", "eq": []}],
    "v_press": [{"n": "Standing Military Press", "eq": ["barbell"], "load": "ohp"}, {"n": "Barbell Shoulder Press", "eq": ["barbell"], "load": "ohp"},
                {"n": "Dumbbell Shoulder Press", "eq": ["dumbbell"]}, {"n": "Arnold Shoulder Press", "eq": ["dumbbell"]},
                {"n": "Cable Shoulder Press", "eq": ["cable"]}, {"n": "Handstand Push-Ups", "eq": []}],
    "v_pull": [{"n": "Pull-ups", "eq": ["pull-up bar"], "reps": "pullups"}, {"n": "Chin Up", "eq": ["pull-up bar"]}, {"n": "Wide-Grip Lat Pulldown", "eq": ["cable"]},
               {"n": "Machine Lat Pulldown", "eq": ["machine"]}, {"n": "Assisted Pull-Up", "eq": ["bands"]}, {"n": "Inverted Row", "eq": []}],
    "h_pull": [{"n": "Seated Cable Row", "eq": ["cable"]}, {"n": "Bent Over Barbell Row", "eq": ["barbell"], "load": "row"},
               {"n": "One-Arm Dumbbell Row", "eq": ["dumbbell"]}, {"n": "Inverted Row", "eq": []}],
    "lateral": [{"n": "Side Lateral Raise", "eq": ["dumbbell"]}, {"n": "Lateral Raises", "eq": ["dumbbell"]}, {"n": "Machine Lateral Raise", "eq": ["machine"]}],
    "rear_delt": [{"n": "Reverse Flyes", "eq": ["dumbbell"]}, {"n": "Reverse Fly Standing", "eq": ["dumbbell"]}, {"n": "Incline Bench Reverse Fly", "eq": ["dumbbell", "bench"]},
                  {"n": "Face pulls with yellow/green band", "eq": ["bands"]}],
    "triceps": [{"n": "Triceps Pushdown", "eq": ["cable"]}, {"n": "Dips", "eq": []}, {"n": "Bench Dips", "eq": ["bench"]}, {"n": "Push-Up", "eq": []}],
    "biceps": [{"n": "Dumbbell Bicep Curl", "eq": ["dumbbell"]}, {"n": "Hammer Curls", "eq": ["dumbbell"]}, {"n": "Barbell Curl", "eq": ["barbell"]}],
    "squat": [{"n": "Barbell Full Squat", "eq": ["barbell"], "load": "squat"}, {"n": "Goblet Squat", "eq": ["dumbbell"]}, {"n": "Leg Press", "eq": ["machine"], "load": "legpress"},
              {"n": "Bodyweight Squat", "eq": []}],
    "hinge": [{"n": "Romanian Deadlift", "eq": ["barbell"]}, {"n": "Dumbbell Romanian Deadlift", "eq": ["dumbbell"]}, {"n": "Glute Bridge", "eq": []}],
    "single_leg": [{"n": "Dumbbell Split Squat", "eq": ["dumbbell"]}, {"n": "Dumbbell Step Ups", "eq": ["dumbbell"]}, {"n": "Split Squats", "eq": []},
                   {"n": "Reverse lunges", "eq": []}, {"n": "Single Leg Glute Bridge", "eq": []}],
    "calves": [{"n": "Standing Calf Raises", "eq": []}, {"n": "Dumbbell Calf Raise", "eq": ["dumbbell"]}, {"n": "Seated Calf Raise", "eq": ["machine"]}],
    "core": [{"n": "Dead bug", "eq": []}, {"n": "Plank", "eq": []}, {"n": "Bird dog", "eq": []}, {"n": "Hanging Leg Raise", "eq": ["pull-up bar"]}],
}

# Exercices écartés selon les zones douloureuses déclarées (S2), par fragments de nom
AVOID = {"genou": ["lunge", "jump", "split squat", "step up", "full squat"], "épaule": ["military", "overhead", "shoulder press", "dips", "handstand", "upright"],
         "dos": ["deadlift", "bent over", "good morning"], "cheville": ["jump", "calf raise"], "hanche": ["deep", "sumo"], "coude": ["dips", "skull", "lying triceps", "preacher", "close-grip", "bench dips", "pushdown", "curl", "push-up", "pushups"], "poignet": ["wrist", "barbell curl"],
         "tendon d'Achille": ["jump", "calf raise"]}
GEAR = {"haltères": ["dumbbell"], "barre et rack": ["barbell", "bench"], "kettlebells": ["kettlebell"], "élastiques": ["bands"], "poids de corps": []}
EXTRA = {"dumbbell": ["bench"]}  # un banc accompagne en général des haltères de salle


@dataclass(frozen=True)
class Slot:
    pattern: str
    role: str  # compound | accessory | core
    base: int  # séries en début de bloc
    top: int  # séries en fin de montée du bloc (progression de volume, M1)
    reps: tuple[str, ...]  # fourchette de répétitions par semaine du bloc : on alourdit au fil des semaines
    technique: str = ""


def _s(pattern: str, role: str, base: int, top: int, reps: str | tuple[str, ...], technique: str = "") -> Slot:
    return Slot(pattern, role, base, top, (reps,) if isinstance(reps, str) else tuple(reps), technique)


LAST_SET = "Dernière série : poussez jusqu'à 0-1 répétition en réserve."
# Séances types : mouvement principal plus lourd et plus volumineux, secondaires intermédiaires, accessoires plus longs ; les fourchettes de
# répétitions s'alourdissent d'une semaine à l'autre du bloc, puis la semaine allégée repart facile.
TEMPLATES: dict[str, list[Slot]] = {
    "upper_a": [_s("h_press", "compound", 4, 5, ("8-10", "6-8", "5-6"), "Série lourde en premier, puis séries un peu plus légères (−5 à −10 %)."),
                _s("v_pull", "compound", 3, 4, ("8-12", "6-10", "6-8")), _s("v_press", "compound", 3, 4, ("8-10", "6-8", "6-8")),
                _s("h_pull", "compound", 3, 4, ("10-12", "8-10", "6-8")), _s("lateral", "accessory", 3, 5, ("15-20", "12-15", "12-15"), LAST_SET),
                _s("triceps", "accessory", 2, 3, ("12-15", "10-15", "10-12"), LAST_SET), _s("core", "core", 2, 3, "30-45 s")],
    "upper_b": [_s("v_pull", "compound", 4, 5, ("8-12", "6-10", "5-8"), "Série lourde en premier, puis séries un peu plus légères (−5 à −10 %)."),
                _s("incline_press", "compound", 3, 4, ("8-12", "6-10", "6-8")), _s("h_pull", "compound", 3, 4, ("10-12", "8-10", "8-10")),
                _s("rear_delt", "accessory", 3, 4, ("15-20", "12-20", "12-15"), LAST_SET),
                _s("biceps", "accessory", 2, 3, ("12-15", "10-12", "8-12"), "En superset avec le triceps : enchaînez sans repos, puis reposez-vous 1 min."),
                _s("triceps", "accessory", 2, 3, ("12-15", "10-15", "10-12"), "En superset avec le biceps : enchaînez sans repos, puis reposez-vous 1 min."),
                _s("core", "core", 2, 3, "30-45 s")],
    "lower": [_s("squat", "compound", 3, 4, ("6-8", "5-6", "4-6"), "Charge lourde, descente contrôlée, aucune série à l'échec."),
              _s("hinge", "compound", 3, 4, ("8", "6-8", "5-6")), _s("single_leg", "accessory", 2, 3, ("10-12", "8-10", "8-10")),
              _s("calves", "accessory", 3, 4, ("12-15", "10-15", "10-12"), LAST_SET), _s("core", "core", 2, 3, "30-45 s")],
    "full": [_s("squat", "compound", 3, 4, ("6-8", "5-6", "4-6")), _s("h_press", "compound", 4, 5, ("8-10", "6-8", "5-6")),
             _s("h_pull", "compound", 3, 4, ("10-12", "8-10", "6-8")), _s("hinge", "compound", 2, 3, ("8", "6-8", "5-6")),
             _s("v_press", "accessory", 2, 3, ("10-12", "8-10", "8-10"), LAST_SET), _s("core", "core", 2, 3, "30-45 s")],
}
TITLES = {"upper_a": "Haut du corps A", "upper_b": "Haut du corps B", "lower": "Jambes et gainage", "full": "Corps entier"}
KIND = {"upper_a": "strength_upper", "upper_b": "strength_upper", "lower": "strength_lower", "full": "strength_full"}

# Intensité par semaine du bloc : on se rapproche de l'échec, puis semaine allégée très facile. Équivalence RIR -> RPE.
RIR_COMPOUND = ["2-3", "2", "1-2"]
RIR_ACCESSORY = ["2-3", "1-2", "0-2"]
RPE = {"2-3": "7-8", "2": "8", "1-2": "8-9", "0-2": "8-10", "4": "6"}
REST = {"compound": "2 à 3 min", "accessory": "1 à 1 min 30", "core": "45 s"}
WHY = {
    "h_press": "Mouvement de base pour les pectoraux, l'avant des épaules et les triceps : c'est lui qui porte la progression de charge.",
    "incline_press": "L'inclinaison cible le haut des pectoraux, important pour un haut du corps dessiné.",
    "v_press": "Construit les épaules et la force de poussée au-dessus de la tête.",
    "v_pull": "Dos large et biceps : l'équilibre indispensable face aux exercices de poussée.",
    "h_pull": "Épaisseur du dos et stabilité des omoplates, qui protègent les épaules.",
    "lateral": "Largeur d'épaules : le deltoïde latéral répond bien à un volume élevé et des répétitions plus longues.",
    "rear_delt": "Deltoïdes arrière et omoplates : posture et santé de l'épaule, souvent sous-travaillés.",
    "triceps": "Les triceps font les deux tiers du volume du bras ; ils sont déjà sollicités par les développés.",
    "biceps": "Complément d'isolation après les tirages, volume modéré.",
    "squat": "Force des jambes, conservée à volume d'entretien pour ne pas gêner la course.",
    "hinge": "Chaîne postérieure (ischio-jambiers, fessiers, dos) : protège le dos et améliore la foulée.",
    "single_leg": "Stabilité et équilibre unilatéral, utile en trail.",
    "calves": "Mollets et tendon d'Achille : prévention des blessures en course.",
    "core": "Tronc gainé pour transmettre la force et protéger le dos.",
}


def _rir(role: str, build: int, deload: bool) -> str:
    if deload:
        return "4"
    if role == "core":
        return ""
    table = RIR_COMPOUND if role == "compound" else RIR_ACCESSORY
    return table[min(build, len(table) - 1)]


def session_plan(variant: str, maintenance: bool, build: int = 0, n_build: int = 3, deload: bool = False, block: int = 1) -> list[dict[str, Any]]:
    """Créneaux d'une séance. `build` : rang de la semaine de montée dans le bloc (0, 1, 2) ; `deload` : semaine allégée.

    Séries : de `base` à `top` au fil des semaines de montée ; −1 en semaine allégée (intensité réduite) ; en entretien (sèche, course proche)
    les jambes perdent une série mais gardent des charges lourdes (M2). `block` : à partir du 2e bloc, les mouvements clés démarrent
    une série plus haut que le bloc précédent (surcharge d'un bloc à l'autre, M8).
    """
    out = []
    for sl in TEMPLATES[variant]:
        frac = build / max(n_build - 1, 1)
        base = min(sl.base + (1 if block >= 2 and sl.role == "compound" else 0), sl.top)
        sets = base + round((sl.top - base) * min(frac, 1.0))
        if deload:
            sets = max(2, sl.base - 1)
        if maintenance and variant == "lower" and sl.role != "core":
            sets = max(2, sets - 1)
        muscle, cue = PATTERNS[sl.pattern]
        rir = _rir(sl.role, build, deload)
        reps = sl.reps[min(1 if deload else build, len(sl.reps) - 1)]
        out.append({"pattern": sl.pattern, "muscle": muscle, "role": sl.role, "sets": str(sets), "reps": reps, "rir": rir,
                    "rpe": RPE.get(rir, ""), "rest": REST[sl.role], "cue": cue, "why": WHY[sl.pattern], "technique": sl.technique})
    return out


def allowed_equipment(facts: dict[str, Any]) -> set[str] | None:
    """None = salle complète (tout matériel). Sinon l'ensemble du matériel canonique disponible."""
    chosen = facts.get("constraints.equipment") or []
    if not chosen or "salle complète" in chosen:
        return None
    have: set[str] = set()
    for c in chosen:
        have |= set(GEAR.get(c, []))
    if "dumbbell" in have:
        have |= set(EXTRA["dumbbell"])
    return have


def start_load(movement: str | None, facts: dict[str, Any], slot: dict[str, Any]) -> float | None:
    """Charge de départ conseillée (kg) depuis le record ou le niveau actuel : estimation Epley, 2 répétitions en réserve."""
    if not movement:
        return None
    b = facts.get(f"bench.{movement}") or {}
    ref = b.get("now") or (b.get("pr") and {**b["pr"], "weight": b["pr"].get("weight", 0) * 0.9})
    if not ref or not ref.get("weight"):
        return None
    e1rm = ref["weight"] * (1 + (ref.get("reps") or 1) / 30)
    top = int(str(slot["reps"]).split("-")[-1])
    w = e1rm / (1 + (top + 2) / 30)
    return round(w / 2.5) * 2.5


def next_target(reps: str, sets: list[dict[str, Any]]) -> dict[str, Any] | None:
    """Objectif de la prochaine séance (double progression) depuis les séries de la dernière fois : on monte les répétitions
    jusqu'au haut de la fourchette sur toutes les séries à la charge de travail, puis on ajoute 2,5 kg."""
    done = [(x.get("kg"), int(x["reps"])) for x in sets if isinstance(x.get("reps"), int | float) and x["reps"] > 0]
    if not done:
        return None
    try:
        top = int(str(reps).split("-")[-1])
    except ValueError:
        return None
    loads = [k for k, _ in done if k]
    if not loads:
        low = min(r for _, r in done)
        return {"kg": None, "reps": top if low >= top else low + 1, "text": (f"Toutes les séries ont atteint {top} répétitions : ajoutez du lest ou une variante plus dure.")
                if low >= top else f"Visez {min(top, low + 1)} répétitions à chaque série."}
    work = max(set(loads), key=lambda k: (loads.count(k), -k))  # charge la plus utilisée (la plus légère en cas d'égalité)
    at_work = [r for k, r in done if k == work]
    if all(r >= top for r in at_work):
        kg = work + 2.5
        return {"kg": kg, "reps": None, "text": f"Séries complètes à {_fmt(work)} kg : passez à {_fmt(kg)} kg."}
    return {"kg": work, "reps": min(top, min(at_work) + 1), "text": f"Gardez {_fmt(work)} kg et visez {min(top, min(at_work) + 1)} répétitions à chaque série."}


def lift_trends(done: list[dict[str, Any]], limit: int = 4) -> dict[str, list[dict[str, Any]]]:
    """Tendance de force par exercice : charge max et 1RM estimé (Epley) des dernières séances terminées, de la plus ancienne à la plus récente."""
    out: dict[str, list[dict[str, Any]]] = {}
    for s in sorted((x for x in done if x["status"] == "done"), key=lambda x: x["day"]):
        for e in (s.get("logged") or {}).get("exercises") or []:
            best = max(((x["kg"], x["reps"]) for x in e.get("sets", []) if isinstance(x.get("kg"), int | float) and x["kg"] > 0
                        and isinstance(x.get("reps"), int | float) and x["reps"] > 0), key=lambda t: t[0] * (1 + t[1] / 30), default=None)
            if best:
                out.setdefault(e["name"], []).append({"jour": s["day"].isoformat(), "kg": best[0], "reps": best[1],
                                                      "e1rm": round(best[0] * (1 + best[1] / 30), 1)})
    return {k: v[-limit:] for k, v in out.items()}


def _fmt(kg: float) -> str:
    return str(int(kg)) if float(kg).is_integer() else str(kg).replace(".", ",")


def annotate_history(sessions: list[dict[str, Any]], past: list[dict[str, Any]]) -> list[dict[str, Any]]:
    """Ajoute à chaque créneau `last` (dernière performance connue) et `target` (objectif conseillé), d'après les séances terminées.
    Retourne des copies : les lignes du dépôt ne sont pas modifiées."""
    done = sorted((s for s in past if s["status"] == "done" and (s.get("logged") or {}).get("exercises")), key=lambda s: s["day"], reverse=True)
    out = []
    for s in sessions:
        slots = (s.get("details") or {}).get("slots")
        if not slots:
            out.append(s)
            continue
        new = []
        for slot in slots:
            name = (slot.get("exercise") or {}).get("name")
            found = None
            for d in done if name and slot.get("role") != "core" else []:
                if d["id"] == s["id"] or d["day"] > s["day"]:
                    continue
                found = next((e for e in d["logged"]["exercises"] if e.get("name") == name
                              and any(isinstance(x.get("reps"), int | float) and x["reps"] > 0 for x in e.get("sets", []))), None)
                if found:
                    found = {"day": d["day"].isoformat(), "sets": [{"kg": x.get("kg"), "reps": x.get("reps")} for x in found["sets"]]}
                    break
            new.append({**slot, "last": found, "target": next_target(slot["reps"], found["sets"]) if found else None} if found else slot)
        out.append({**s, "details": {**s["details"], "slots": new}})
    return out


def resolve(repo: Repo, slots: list[dict[str, Any]], facts: dict[str, Any]) -> list[dict[str, Any]]:
    have = allowed_equipment(facts)
    avoid = [w for inj in (facts.get("history.injuries") or []) for w in AVOID.get(inj, [])]
    used: set[int] = set()
    out = []
    for slot in slots:
        item = dict(slot)
        for cand in CANDIDATES[slot["pattern"]]:
            if have is not None and not set(cand["eq"]) <= have:
                continue
            if any(a in cand["n"].lower() for a in avoid):
                continue
            rows, _ = repo.search_exercises(cand["n"], None, None, None, 80, 0)
            ex = next((e for e in rows if e.id not in used and cand["n"].lower() in {(e.name_en or "").lower(), e.name.lower()}), None)
            if not ex:
                continue
            used.add(ex.id)
            main = next((m for m in ex.media if m.kind == "image"), None)
            item["exercise"] = {"id": ex.id, "name": ex.name, "thumb": main.id if main else None}
            kg = start_load(cand.get("load"), facts, slot)
            if kg:
                item["suggested_kg"] = kg
            break
        if "exercise" not in item and avoid and slot["pattern"] in ("triceps", "biceps"):
            continue  # zone douloureuse déclarée : pas d'isolation du bras plutôt qu'un exercice qui charge la zone
        out.append(item)
    return out
