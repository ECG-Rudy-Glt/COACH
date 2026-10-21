"""Programmation hybride CrossFit et Hyrox (M10, M14 à M21, I7) : forme de la semaine, alternance dur/facile, progression, blessures, mixte."""
import re
from datetime import date, timedelta
from itertools import product

import pytest
import yaml

from app.coach import service
from app.plan import hybrid as HB
from app.plan import hyrox as HY
from app.plan.engine import DAYS, advice, build_profile, outlook, plan_weeks
from tests.test_plan import RUDY, TODAY, by_week

MONDAY = date(2026, 10, 12)
BASE = {"constraints.training_days": 4, "constraints.weekday_session_max_min": 75, "constraints.weekend_session_max_min": 150, "strength.level": "intermédiaire",
        "body.birth_year": 1995, "history.recent_break": "non", "history.injuries": ["aucune"], "running.best_10k_min": 50}
RULES = set(yaml.safe_load((service.ROOT / "data" / "rules_digest.yaml").read_text(encoding="utf-8")))


def ev(title, d, priority="principal", **details):
    return {"status": "active", "kind": "event", "target_date": d, "priority": priority, "title": title, "details": details}


def weeks(facts, goals=(), n=8, start=MONDAY):
    p = build_profile({**BASE, **facts}, list(goals), TODAY)
    return p, list(by_week(plan_weeks(p, TODAY, weeks=n, start=start)).values())


def cf(**kw):
    return {"sports.practiced": ["crossfit"], **kw}


def hx(**kw):
    return {"sports.practiced": ["hyrox"], **kw}


def hybrid_slot(s):
    return HB.SLOTS.get(s.details.get("variant", ""))


def text(sessions):
    return " ".join(" ".join(b["items"]) + b["title"] for s in sessions for b in s.details.get("blocks", [])) + " ".join(s.details.get("format", "") for s in sessions)


# ---------- CrossFit : microcycle (M10) ----------
@pytest.mark.parametrize("days", [2, 3, 4, 5, 6])
def test_crossfit_week_has_as_many_distinct_sessions_as_available_days(days):
    p, wk = weeks(cf(**{"constraints.training_days": days}), n=4)
    assert p.dedicated and p.hybrid == "crossfit"
    for ss in wk:
        assert len(ss) == days and len({s.date for s in ss}) == days, [s.title for s in ss]
        variants = [s.details["variant"] for s in ss]
        assert len(set(variants)) >= min(days, 5)  # des séances distinctes : seul le 2e metcon ressemble à un autre
        assert "cf_force_lower" in variants and "cf_metcon" in variants
        assert all(s.kind == "strength_crossfit" and s.rules and "M10" in s.rules for s in ss)
    kinds = {s.details["variant"] for s in wk[0]}
    assert ("cf_aerobic" in kinds) == (days >= 4) and ("cf_force_upper" in kinds) == (days >= 5) and ("cf_gym" in kinds) == (days >= 3)


def test_crossfit_is_limited_by_blocked_days_and_keeps_a_rest_day():
    _, wk = weeks(cf(**{"constraints.training_days": 6, "multisport.blocked_days": ["lundi", "mardi", "samedi"]}), n=4)
    for ss in wk:
        assert len(ss) <= 3 and not {s.date.weekday() for s in ss} & {0, 1, 5}


def test_hard_days_never_touch_on_the_same_muscle_groups():
    """M14 / G5 : pas de séance dure collée à une autre séance dure sur les mêmes groupes, même d'une semaine à l'autre (dimanche, lundi)."""
    for days, blocked in product([3, 4, 5, 6], [[], ["vendredi"], ["lundi", "mardi"], ["samedi", "dimanche"]]):
        for sport in (cf, hx):
            p, wk = weeks(sport(**{"constraints.training_days": days, "multisport.blocked_days": blocked}), n=8)
            for ss in wk:
                assert len({s.date.weekday() for s in ss}) <= 6, "G5 : un jour de repos"
                hard = [(s.date.weekday(), s) for s in ss if hybrid_slot(s) and hybrid_slot(s).load >= 2 and not s.details["cycle"]["deload"]]
                for (d1, a), (d2, b) in product(hard, hard):
                    if a is not b and (d1 - d2) % 7 == 1:
                        assert not HB.clash(hybrid_slot(a), hybrid_slot(b)), (days, blocked, a.title, b.title)
                assert not {s.date.weekday() for s in ss} & p.blocked, "G6"


def test_crossfit_block_progression_and_deload():
    """M8, M15 : la charge de travail monte dans le bloc, le bloc suivant démarre plus haut, la décharge est légère ; les formats de metcon varient."""
    _, wk = weeks(cf(**{"constraints.training_days": 5}), n=8)
    sets = []
    for ss in wk:
        lower = next(s for s in ss if s.details["variant"] == "cf_force_lower")
        m = re.search(r"(\d+) séries de (\d+), (\d+) répétitions en réserve", lower.details["blocks"][1]["items"][0])
        sets.append(tuple(int(x) for x in m.groups()))
    assert sets[0][0] < sets[1][0] < sets[2][0] and sets[2][2] < sets[0][2], "séries en hausse, répétitions en réserve en baisse"
    assert sets[3] == (3, 5, 4), "décharge"
    assert sets[4][0] > sets[0][0], "le bloc 2 démarre une série plus haut (M8)"
    fmts = [next(s for s in ss if s.details["variant"] == "cf_metcon").details["blocks"][1]["title"] for ss in wk]
    assert len({f.split(" ")[2] for f in fmts[:3]}) == 3, fmts[:3]  # AMRAP, For Time, EMOM : formats distincts dans le bloc
    assert fmts[3].endswith("AMRAP 8 min, allure confortable")
    aero = [next(s for s in ss if s.details["variant"] == "cf_aerobic").duration_min for ss in wk]
    assert aero[1] >= aero[0] and aero[3] < aero[2]


def test_crossfit_level_scales_gymnastics_and_metcons():
    def gym(level):
        _, wk = weeks(cf(**{"hybrid.crossfit_years": level, "constraints.training_days": 4}), n=2)
        return text([s for s in wk[1] if s.details["variant"] in ("cf_gym", "cf_metcon")])

    novice, expert = gym(0), gym(5)
    assert "Rowing aux anneaux" in novice and "Toes-to-bar" not in novice.replace("toes-to-bar", "")
    assert "Toes-to-bar" in expert and "Tractions strictes" in expert and "Rowing aux anneaux" not in expert
    assert build_profile({**BASE, **cf(**{"hybrid.crossfit_years": 5})}, [], TODAY).hy_level == "avancé"
    assert build_profile({**BASE, **cf()}, [], TODAY).hy_level == "intermédiaire"  # à défaut, niveau de musculation déclaré


@pytest.mark.parametrize("injury,banned", [("genou", ["squat", "burpees", "wall balls", "thrusters", "fentes", "push press"]),
                                           ("épaule", ["développé militaire", "push press", "arraché", "thrusters", "pompes en équilibre"]),
                                           ("dos", ["soulevé de terre", "swings", "rowing barre"])])
def test_declared_injury_removes_the_matching_moves(injury, banned):
    """S2 : les mouvements liés à la zone sont remplacés, jamais proposés."""
    _, wk = weeks(cf(**{"constraints.training_days": 6, "history.injuries": [injury]}), n=8)
    allt = text([s for ss in wk for s in ss]).lower()
    for word in banned:
        assert word not in allt, (injury, word)
    assert any("variante" in n for s in wk[0] for n in s.notes)


def test_crossfit_session_durations_respect_the_user_maximum():
    _, wk = weeks(cf(**{"constraints.training_days": 5, "constraints.weekday_session_max_min": 50, "constraints.weekend_session_max_min": 70}), n=4)
    for ss in wk:
        for s in ss:
            assert s.duration_min <= (70 if s.date.weekday() >= 5 else 50), (s.title, s.duration_min)
            assert s.duration_min == sum(b["minutes"] for b in s.details["blocks"]) and all("optional" not in b for b in s.details["blocks"])


# ---------- Hyrox ----------
def week_run_load(ss):
    return sum(s.duration_min for s in ss if s.kind.startswith("run_")) + sum(s.details.get("run_min", 0) for s in ss)


def test_hyrox_week_mixes_runs_stations_and_compromised_running():
    _, wk = weeks(hx(**{"constraints.training_days": 4}), n=4)
    titles = [[s.title for s in ss] for ss in wk]
    assert all(len(ss) == 4 for ss in wk)
    flat = {t for ts in titles for t in ts}
    assert {"Hyrox — stations", "Hyrox — course compromise", "Footing facile", "Séance de qualité (Hyrox)"} <= flat
    for ss in wk:
        assert any(s.kind.startswith("run_") for s in ss) and any(s.details.get("variant") == "hy_stations" for s in ss) and any(s.details.get("variant") == "hy_comp" for s in ss)
    _, wk5 = weeks(hx(**{"constraints.training_days": 5}), n=2)
    assert any(s.kind == "strength_upper" for s in wk5[1]) and len(wk5[1]) == 5
    _, wk6 = weeks(hx(**{"constraints.training_days": 6}), n=2)
    assert any(s.details.get("variant") == "hy_cross" for s in wk6[1]) and len(wk6[1]) == 6


def test_hyrox_loads_follow_category_level_and_never_exceed_the_standard():
    assert HY.standard_for("Pro", "homme")["sled_push"] == 202 and HY.standard_for("Open", "femme") == {"sled_push": 102, "sled_pull": 78, "farmer": 16, "lunges": 10, "wallballs": 4}
    assert HY.standard_for("Doubles", None) == HY.STANDARD[("open", "m")] and HY.standard_for("Pro", "femme")["wallballs"] == 6

    def sled(facts):
        _, wk = weeks(hx(**facts), n=8)
        loads = [int(m) for ss in wk for s in ss for m in re.findall(r"Poussée de traîneau : \d+ m, (\d+) kg", text([s]))]
        return loads

    open_m = sled({"hybrid.hyrox_done": "jamais"})
    assert open_m and max(open_m) <= 152
    pro_m = sled({"hybrid.hyrox_category": "Pro", "hybrid.hyrox_done": "plusieurs fois"})
    open_f = sled({"body.sex_for_calc": "femme", "hybrid.hyrox_done": "jamais"})
    assert max(pro_m) <= 202 and max(pro_m) > max(open_m) and max(open_f) <= 102 and max(open_f) < max(open_m)
    assert max(open_m[:len(open_m) // 2]) <= max(open_m[len(open_m) // 2:]), "la charge monte au fil des blocs"


def test_hyrox_run_volume_follows_g1_and_g2():
    p, wk = weeks(hx(**{"constraints.training_days": 5, "running.weekly_km_8w": 25}), n=8)
    loads = [week_run_load(ss) for ss in wk]
    for i in range(1, len(loads)):
        if not wk[i][0].details["cycle"]["deload"] and not wk[i - 1][0].details["cycle"]["deload"]:
            assert loads[i] <= loads[i - 1] * 1.12 + 5, loads
    assert loads[3] < loads[2] and loads[7] < loads[6], f"G2 : {loads}"


def test_hyrox_event_schedules_partial_then_full_simulation_and_taper():
    event = ev("Hyrox Paris", date(2026, 12, 6), distance_km=8)
    p, wk = weeks(hx(**{"constraints.training_days": 4}), [event], n=8)
    assert p.event["hyrox"] and p.event["distance_km"] == 0, "les 8 km sont dans l'épreuve, pas un objectif de course"
    variants = [[s.details.get("variant") for s in ss] for ss in wk]
    assert "hy_half" in variants[2] and "hy_sim" in variants[4], variants
    assert sum(v.count("hy_sim") for v in variants) == 1, "une seule simulation complète"
    assert "hy_sim" not in variants[3] and "hy_half" not in variants[3]
    full = next(s for s in wk[4] if s.details.get("variant") == "hy_sim")
    assert "8." in text([full]) and full.duration_min <= 150 and len(re.findall(r"1 km de course, puis", text([full]))) == 8
    for taper_week in wk[6:]:
        assert all("(allégée)" in s.title or s.kind.startswith("run_") for s in taper_week), [s.title for s in taper_week]
        assert not any(s.details.get("variant") in ("hy_sim", "hy_half") for s in taper_week)
    assert max(week_run_load(wk[6]), 1) <= week_run_load(wk[5]), "affûtage : volume de course en baisse"
    assert outlook(p, TODAY) is None and not any("distance" in a for a in advice(p))


def test_hyrox_day_before_and_after_the_race_are_free_of_hard_sessions():
    d = date(2026, 10, 25)  # dimanche
    p, wk = weeks(hx(**{"constraints.training_days": 5}), [ev("Hyrox Lyon", d)], n=3)
    around = [s for ss in wk for s in ss if abs((s.date - d).days) <= 2]
    assert not [s for s in around if s.date == d], "le jour de l'épreuve est la séance"
    assert not [s for s in around if s.date == d - timedelta(days=1) and s.kind in ("strength_crossfit", "strength_lower") or (s.date > d and s.kind != "strength_upper")]


def test_hyrox_without_event_runs_a_half_simulation_every_eight_weeks_at_most():
    _, wk = weeks(hx(**{"constraints.training_days": 4}), n=12)
    halves = [i for i, ss in enumerate(wk) if any(s.details.get("variant") == "hy_half" for s in ss)]
    assert halves == [6], halves  # 3e semaine du 2e bloc


def test_hyrox_weak_stations_come_first_and_equipment_is_replaced():
    _, wk = weeks(hx(**{"hybrid.hyrox_weak_stations": ["wall balls", "farmers carry"], "constraints.training_days": 4}), n=2)
    first = next(s for s in wk[1] if s.details.get("variant") == "hy_stations" or s.details.get("variant") == "hy_comp")
    assert first
    allt = text([s for s in wk[0] + wk[1] if s.details.get("variant") == "hy_stations"])
    assert "Wall balls" in allt or "Farmers carry" in allt
    _, wk2 = weeks(hx(**{"hybrid.access": "aucun lieu fixe", "constraints.training_days": 4}), n=2)
    t2 = text([s for ss in wk2 for s in ss])
    assert "Poussée de traîneau" not in t2 and "Fentes marchées lestées" in t2


def test_hyrox_injury_replaces_stations_and_running_when_the_zone_carries_the_run():
    _, wk = weeks(hx(**{"constraints.training_days": 5, "history.injuries": ["genou"], "running.weekly_km_8w": 25}), n=8)
    allt = text([s for ss in wk for s in ss]).lower()
    for word in ("poussée de traîneau", "burpee broad", "fentes avec", "wall balls", "1 km de course"):
        assert word not in allt, word
    assert not any(s.kind == "run_quality" for ss in wk for s in ss), "S2 : pas d'intensité de course"
    loads = [sum(s.duration_min for s in ss if s.kind.startswith("run_")) for ss in wk if not ss[0].details["cycle"]["deload"]]
    assert max(loads) <= min(loads) * 1.05 + 1, f"S2 : volume de course gelé {loads}"
    assert not any("run_min" in s.details and s.details["run_min"] for ss in wk for s in ss)


@pytest.mark.parametrize("facts", [cf(), hx(), {"sports.practiced": ["hyrox", "running"]}, {"sports.practiced": ["crossfit", "strength"]}])
def test_red_flag_blocks_every_hybrid_plan(facts):
    """S1."""
    p = build_profile({**BASE, **facts, "health.red_flags": ["douleur thoracique"]}, [], TODAY)
    assert plan_weeks(p, TODAY, weeks=4) == []
    ok = build_profile({**BASE, **facts, "health.red_flags": ["douleur thoracique"], "health.red_flags_discussed": "oui"}, [], TODAY)
    assert plan_weeks(ok, TODAY, weeks=2)


def test_every_cited_rule_exists_and_plans_are_deterministic():
    for facts in (cf(**{"constraints.training_days": 6}), hx(**{"constraints.training_days": 6}), {"sports.practiced": ["hyrox", "running", "strength"], "constraints.training_days": 5}):
        _, a = weeks(facts, [ev("Hyrox Nantes", date(2026, 12, 6))], n=8)
        _, b = weeks(facts, [ev("Hyrox Nantes", date(2026, 12, 6))], n=8)
        assert [[(s.date, s.title, s.duration_min, s.details, s.rules) for s in ss] for ss in a] == [[(s.date, s.title, s.duration_min, s.details, s.rules) for s in ss] for ss in b]
        for ss in a:
            for s in ss:
                assert s.rules and set(s.rules) <= RULES, (s.title, set(s.rules) - RULES)


# ---------- mixte (I7) ----------
def hybrid_sessions(ss):
    return [s for s in ss if s.kind == "strength_crossfit"]


def test_hyrox_with_running_keeps_the_key_runs_and_one_hybrid_session():
    p, wk = weeks({"sports.practiced": ["hyrox", "running"], "constraints.training_days": 5, "running.weekly_km_8w": 30}, n=8)
    assert not p.dedicated and p.runs
    for ss in wk:
        hs = hybrid_sessions(ss)
        assert len(hs) <= 1
        assert any(s.kind == "run_long" for s in ss)
        for h in hs:
            assert "I7" in h.rules
            for k in (s for s in ss if s.kind in ("run_long", "run_quality", "strength_lower")):
                assert abs((k.date - h.date).days) >= 2 or k.kind == "run_easy", (h.title, k.title)
    assert sum(len(hybrid_sessions(ss)) for ss in wk) >= 6
    variants = {h.details["variant"] for ss in wk for h in hybrid_sessions(ss)}
    assert {"hy_stations", "hy_comp"} <= variants, "stations et course compromise alternent"
    # G1 : la course des séances hybrides est comprise dans le volume de course de la semaine
    loads = [week_run_load(ss) for ss in wk]
    for i in range(1, len(loads)):
        if not wk[i][0].details["cycle"]["deload"] and not wk[i - 1][0].details["cycle"]["deload"]:
            assert loads[i] <= loads[i - 1] * 1.15 + 5, loads


def test_run_event_still_wins_over_hybrid_sessions():
    near = ev("Trail 50 km", date(2026, 11, 14), distance_km=50, elevation_m=2500)
    _, wk = weeks({"sports.practiced": ["running", "strength", "crossfit"]}, [near], n=4)
    assert not any(hybrid_sessions(ss) for ss in wk), "M9 : la course l'emporte près de l'objectif"
    _, wk2 = weeks({"sports.practiced": ["running", "strength", "hyrox"]}, [near], n=4)
    kept = [h for ss in wk2 for h in hybrid_sessions(ss)]
    assert kept and {h.details["variant"] for h in kept} == {"hy_stations"} and all("(allégée)" in h.title for h in kept), "entretien : stations légères, jamais de compromise"


def test_crossfit_with_running_and_without_strength_adds_gymnastics_only_with_four_days():
    _, wk4 = weeks({"sports.practiced": ["crossfit", "running"], "constraints.training_days": 5, "running.weekly_km_8w": 30}, n=4)
    assert all(len(hybrid_sessions(ss)) == 2 for ss in wk4)
    _, wk3 = weeks({"sports.practiced": ["crossfit", "running"], "constraints.training_days": 3, "running.weekly_km_8w": 30}, n=4)
    assert all(len(hybrid_sessions(ss)) <= 1 for ss in wk3)


def test_mixed_profiles_never_break_global_rules():
    from tests.test_plan import check_rules

    sports_opts = [["hyrox", "running"], ["crossfit", "running", "strength"], ["hyrox", "strength"], ["crossfit", "hyrox", "running"]]
    for days, blocked, sports in product([3, 4, 5, 6], [[], ["vendredi"], ["samedi", "dimanche"]], sports_opts):
        facts = {**RUDY, "constraints.training_days": days, "multisport.blocked_days": blocked, "sports.practiced": sports}
        p = build_profile(facts, [], TODAY)
        sessions = plan_weeks(p, TODAY, weeks=6)
        check_rules(p, sessions)
        for ss in by_week(sessions).values():
            day_load = {}
            for s in ss:
                day_load.setdefault(s.date, []).append(s)
            assert all(sum(1 for x in v if x.kind.startswith("strength")) <= 1 for v in day_load.values())


def test_hybrid_sessions_are_translated_to_english_without_leftover_french():
    from app import i18n

    french = re.compile(r"[àâçéèêëîïôûùüÿœ]|\b(séries|répétitions|réserve|puis|tours|repos|charge|course|avec|pour|sur|dans|vous|chaque|jamais|faibles|séance)\b")
    for facts in (cf(**{"constraints.training_days": 6}), hx(**{"constraints.training_days": 6}), {"sports.practiced": ["hyrox", "running"], "constraints.training_days": 5}):
        _, wk = weeks(facts, [ev("Hyrox Paris", date(2026, 12, 6))], n=8)
        for ss in wk:
            for s in ss:
                if s.kind in ("strength_crossfit", "run_quality"):
                    bits = [s.title, *s.notes, *(s.details.get("format", ""),), *(i for b in s.details.get("blocks", []) for i in [b["title"], *b["items"], b.get("effort", "")])]
                    for bit in bits:
                        if bit:
                            assert not french.search(i18n.tr(bit, "en")), (bit, i18n.tr(bit, "en"))


def test_days_constant_is_unchanged():
    assert DAYS[0] == "lundi" and len(DAYS) == 7


# ---------- sécurité et alimentation sur ces profils (S1 à S6) ----------
def test_safety_rules_hold_for_hybrid_profiles():
    """S1 (plan vide si signal d'alerte), S2 (blessure), S3 (≤ 1 % par semaine), S4 et S6 (pas de déficit), S5 (jamais sous le métabolisme de base)."""
    from app.nutrition import engine as nut

    day = date(2026, 10, 18)
    for sports, days in product([["crossfit"], ["hyrox"], ["hyrox", "running"], ["crossfit", "strength"]], [3, 5]):
        facts = {**BASE, "sports.practiced": sports, "constraints.training_days": days, "goal.weight_direction": "perdre", "body.weight_kg": 60, "body.height_cm": 160,
                 "body.sex_for_calc": "femme"}
        plan = plan_weeks(build_profile(facts, [], TODAY), TODAY, weeks=2)
        sessions = [{"kind": s.kind, "duration_min": s.duration_min} for s in plan]
        assert sessions
        p = nut.build_profile(facts, day, None, sessions, None)
        tg = nut.targets(p)
        assert tg["rate_pct_per_week"] <= 1.0 and tg["kcal"] >= tg["bmr"] and tg["kcal"] >= nut.MIN_KCAL["femme"], tg  # S3, S5
        for blocked in ({"body.birth_year": 2012}, {"health.conditions": ["trouble alimentaire passé"]}, {"health.conditions": ["grossesse ou post-partum"]}):
            b = nut.build_profile({**facts, **blocked}, day, None, sessions, None)
            assert nut.targets(b)["deficit_kcal"] == 0, blocked  # S4, S6
        flag = build_profile({**facts, "health.red_flags": ["malaise"]}, [], TODAY)
        assert plan_weeks(flag, TODAY, weeks=2) == []  # S1


def test_hybrid_sessions_count_more_than_the_default_for_energy_needs():
    from app.nutrition import engine as nut

    facts = {**BASE, "body.sex_for_calc": "homme", "body.weight_kg": 75, "body.height_cm": 178}
    day = date(2026, 10, 18)
    hy = nut.targets(nut.build_profile(facts, day, None, [{"kind": "strength_crossfit", "duration_min": 60}] * 4, None))
    other = nut.targets(nut.build_profile(facts, day, None, [{"kind": "unknown", "duration_min": 60}] * 4, None))
    assert hy["tdee"] > other["tdee"]


def test_full_simulation_replaces_the_long_run_when_running_is_declared():
    _, wk = weeks({"sports.practiced": ["hyrox", "running"], "constraints.training_days": 5, "running.weekly_km_8w": 30}, [ev("Hyrox Paris", date(2026, 12, 6))], n=8)
    sim_weeks = [ss for ss in wk if any(s.details.get("variant") == "hy_sim" for s in ss)]
    assert len(sim_weeks) == 1 and not any(s.kind == "run_long" for s in sim_weeks[0])
    assert all(any(s.kind == "run_long" for s in ss) for ss in wk[:4])
    sim = next(s for s in sim_weeks[0] if s.details.get("variant") == "hy_sim")
    assert sim.date.weekday() in (5, 6) and sim.duration_min > 75, "la simulation complète tient dans la durée du week-end"
