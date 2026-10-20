from datetime import date, timedelta
from itertools import product

from app.plan.engine import DAYS, Profile, build_profile, plan_weeks

TODAY = date(2026, 10, 7)  # mercredi

RUDY = {
    "sports.practiced": ["running", "strength", "trail"], "goal.weight_direction": "perdre",
    "goal.physique_focus": ["haut du corps"], "constraints.training_days": 5,
    "constraints.weekday_session_max_min": 75, "constraints.weekend_session_max_min": 180,
    "multisport.blocked_days": ["vendredi"], "running.weekly_km_8w": 30, "running.best_10k_min": 46,
    "running.hr_max": 188, "strength.sessions_per_week": 3, "strength.level": "intermédiaire",
    "body.birth_year": 1995, "history.recent_break": "non", "history.injuries": ["aucune"],
}
EVENT = {"status": "active", "kind": "event", "target_date": date(2027, 2, 20), "priority": "principal",
         "title": "Trail 50 km", "details": {"distance_km": 50, "elevation_m": 2500}}


def by_week(sessions):
    weeks: dict[date, list] = {}
    for s in sessions:
        weeks.setdefault(s.date - timedelta(days=s.date.weekday()), []).append(s)
    return dict(sorted(weeks.items()))


def run_minutes(ss):
    return sum(s.duration_min for s in ss if s.kind.startswith("run_"))


def check_rules(p: Profile, sessions):
    for ss in by_week(sessions).values():
        days = {s.date.weekday() for s in ss}
        assert not days & p.blocked, "G6 : jour bloqué utilisé"
        assert len(days) <= 6, "G5 : au moins un jour de repos"
        kinds = [s.kind for s in ss]
        assert kinds.count("run_quality") <= 1, "C1 : une séance de qualité au plus"
        total = run_minutes(ss)
        for s in ss:
            if s.kind == "run_long" and total and sum(1 for x in ss if x.kind.startswith("run_")) >= 3:
                assert s.duration_min <= max(0.36 * total, 35), "C2 : sortie longue ≤ ~30 % du volume"
            if s.kind == "strength_lower":
                d = s.date.weekday()
                key_days = {x.date.weekday() for x in ss if x.kind in ("run_long", "run_quality")}
                assert d not in key_days, "I1 : jambes et séance clé le même jour"
                assert (d + 1) % 7 not in key_days, "I2 : jambes la veille d'une séance clé"
                long_days = {x.date.weekday() for x in ss if x.kind == "run_long"}
                assert (d - 1) % 7 not in long_days, "jambes le lendemain de la sortie longue"
        for s in ss:
            assert s.rules and s.duration_min > 0, "toute séance cite ses règles"


def test_reference_profile_respects_rules():
    p = build_profile(RUDY, [EVENT], TODAY)
    sessions = plan_weeks(p, TODAY, weeks=6)
    assert sessions and all(s.date >= TODAY for s in sessions)
    check_rules(p, sessions)
    assert p.event["distance_km"] == 50 and p.hr_max == 188


def test_volume_progression_and_deload():
    p = build_profile({**RUDY, "history.recent_break": "non"}, [], TODAY)
    weeks = list(by_week(plan_weeks(p, date(2026, 10, 5), weeks=8)).values())
    vols = [run_minutes(w) for w in weeks]
    for i in range(1, len(vols)):
        is_deload_next = (i % p.deload_cycle) == p.deload_cycle - 1
        if not is_deload_next and (i - 1) % p.deload_cycle != p.deload_cycle - 1 and vols[i - 1]:
            assert vols[i] <= vols[i - 1] * 1.12 + 5, f"G1 semaine {i}: {vols}"
    d = p.deload_cycle - 1
    assert vols[d] < vols[d - 1], f"G2 : semaine allégée {vols}"


def test_older_or_returning_runner_gets_2_plus_1():
    assert build_profile({**RUDY, "body.birth_year": 1975}, [], TODAY).deload_cycle == 3
    assert build_profile({**RUDY, "history.recent_break": "oui blessure"}, [], TODAY).deload_cycle == 3
    assert build_profile(RUDY, [], TODAY).deload_cycle == 4


def test_red_flag_blocks_plan_until_discussed():
    flagged = {**RUDY, "health.red_flags": ["palpitations"]}
    assert plan_weeks(build_profile(flagged, [], TODAY), TODAY) == []  # S1
    ok = {**flagged, "health.red_flags_discussed": "oui"}
    assert plan_weeks(build_profile(ok, [], TODAY), TODAY)


def test_event_close_makes_legs_maintenance_and_caps_strength():
    near = {**EVENT, "target_date": TODAY + timedelta(days=42)}
    p = build_profile(RUDY, [near], TODAY)
    sessions = plan_weeks(p, TODAY, weeks=2)
    for w in by_week(sessions).values():
        assert sum(1 for s in w if s.kind.startswith("strength")) <= 2  # décision 3
        for s in w:
            if s.kind == "strength_lower":
                assert "entretien" in s.title


def test_many_availability_combinations_never_break_rules():
    blocked_opts = [[], ["vendredi"], ["lundi", "mardi"], ["samedi", "dimanche"]]
    for days, blocked, sports in product([2, 3, 4, 5, 6], blocked_opts, [["running"], ["strength"], ["running", "strength"]]):
        facts = {**RUDY, "constraints.training_days": days, "multisport.blocked_days": blocked,
                 "sports.practiced": sports}
        p = build_profile(facts, [], TODAY)
        sessions = plan_weeks(p, TODAY, weeks=5)
        check_rules(p, sessions)
        assert all(DAYS[s.date.weekday()] not in blocked for s in sessions)


def test_no_sport_gives_empty_plan():
    assert plan_weeks(build_profile({"sports.practiced": ["cycling"]}, [], TODAY), TODAY) == []


def test_plan_api_generate_read_log_and_regenerate_keeps_current_week():
    from fastapi.testclient import TestClient

    from app.auth import reset_rate_limits
    from app.exercises.models import Exercise
    from app.main import app, get_repo
    from app.repo import MemoryRepo

    reset_rate_limits()
    repo = MemoryRepo()
    repo.replace_exercises([Exercise(source="t", source_id=str(i), name=n, name_en=n, kind="strength", muscles_primary=["chest"],
                                     equipment=["barbell"], license="L") for i, n in enumerate(
        ["Bench Press", "Barbell Full Squat", "Goblet Squat", "Dumbbell Split Squat", "Reverse lunges", "Romanian Deadlift", "Plank",
         "Pull-ups", "Seated Cable Row", "Standing Military Press", "Side Lateral Raise"])])
    app.dependency_overrides[get_repo] = lambda: repo
    try:
        c = TestClient(app)
        uid = c.post("/auth/register", json={"name": "R", "email": "p@example.org", "password": "un-mot-de-passe-solide"}).json()["id"]
        assert c.post(f"/users/{uid}/plan/generate").json()["reason"]  # sans sport : pas de plan
        for q, v in [("goal.sports", ["running", "strength"]), ("con.days", 4), ("his.injuries", ["genou"])]:
            c.post(f"/users/{uid}/answers", json={"question_id": q, "value": v})
        r = c.post(f"/users/{uid}/plan/generate").json()
        assert r["created"] > 0 and r["reason"] is None
        plan = c.get(f"/users/{uid}/plan").json()
        assert plan["sessions"] and all(s["rules"] for s in plan["sessions"])
        lower = [s for s in plan["sessions"] if s["kind"] == "strength_lower"]
        names = [sl["exercise"]["name"] for s in lower for sl in s["details"]["slots"] if "exercise" in sl]
        assert names and not any(x in n.lower() for n in names for x in ("lunge", "split squat", "full squat"))  # S2 : genou déclaré
        sid = plan["sessions"][0]["id"]
        done = c.patch(f"/users/{uid}/plan/sessions/{sid}", json={"status": "done", "logged": {"rpe": 6, "note": "ok"}}).json()
        assert done["status"] == "done" and done["logged"]["rpe"] == 6
        before = {s["id"] for s in c.get(f"/users/{uid}/plan").json()["sessions"] if s["day"] <= date.today().isoformat()}
        again = c.post(f"/users/{uid}/plan/generate").json()  # régénération : la semaine en cours reste intacte
        assert date.fromisoformat(again["from"]) > date.today()
        after = {s["id"] for s in c.get(f"/users/{uid}/plan").json()["sessions"] if s["day"] <= date.today().isoformat()}
        assert before == after
        assert c.patch(f"/users/{uid}/plan/sessions/9999", json={"status": "done"}).status_code == 404
    finally:
        app.dependency_overrides.clear()


def _strength_week(facts_extra=None, today=TODAY, **kw):
    facts = {**RUDY, "sports.practiced": ["running", "strength"], "strength.sessions_per_week": 3, **(facts_extra or {})}
    p = build_profile(facts, kw.get("goals", []), today)
    return p, by_week(plan_weeks(p, today, weeks=4))


def test_three_sessions_give_upper_body_twice_with_balanced_pull_and_core():
    p, weeks = _strength_week({"history.recent_break": "non", "running.weekly_km_12m": 30, "running.weeks_since_last_run": 0})
    for ss in list(weeks.values())[1:3]:
        strength = [s for s in ss if s.kind.startswith("strength")]
        variants = sorted(s.details["variant"] for s in strength)
        assert variants == ["lower", "upper_a", "upper_b"]
        slots = [sl for s in strength if s.kind == "strength_upper" for sl in s.details["slots"]]
        push = sum(int(sl["sets"]) for sl in slots if sl["pattern"] in ("h_press", "incline_press", "v_press", "triceps"))
        pull = sum(int(sl["sets"]) for sl in slots if sl["pattern"] in ("v_pull", "h_pull", "rear_delt", "biceps"))
        assert pull >= push - 1, "au moins autant de tirage que de poussée"
        assert {sl["muscle"] for sl in slots} >= {"chest", "lats", "middle back", "shoulders", "triceps", "biceps"}
        for s in strength:  # polyarticulaires d'abord, gainage en dernier
            roles = [sl["role"] for sl in s.details["slots"]]
            assert roles[0] == "compound" and roles[-1] == "core"
            assert all(sl["cue"] for sl in s.details["slots"])


def test_return_from_break_ramps_to_usual_volume_not_from_zero_forever():
    facts = {**RUDY, "sports.practiced": ["running"], "running.weekly_km_8w": 1, "running.weekly_km_12m": 30, "running.weeks_since_last_run": 1,
             "constraints.training_days": 5}
    p = build_profile(facts, [], TODAY)
    from app.plan.engine import weekly_volumes
    vols = [v for v, dl, tp in weekly_volumes(p, 8, None)]
    usual_min = 30 * p.easy_pace
    assert vols[0] >= 0.5 * usual_min - 1, "reprise à 50 % du volume habituel (arrêt court)"
    builds = [v for i, v in enumerate(vols) if i % p.deload_cycle != p.deload_cycle - 1]
    assert all(b2 <= b1 * 1.16 + 1 for b1, b2 in zip(builds, builds[1:], strict=False)), f"G3/G1 : {vols}"
    assert max(vols) >= 0.9 * usual_min, "le volume habituel est retrouvé en quelques semaines"
    p2 = build_profile({**facts, "running.weeks_since_last_run": 30}, [], TODAY)
    assert weekly_volumes(p2, 1, None)[0][0] < vols[0], "arrêt long : départ plus bas (30 %)"


def test_uses_declared_training_days_with_enough_volume():
    facts = {**RUDY, "running.weekly_km_8w": 30, "running.weekly_km_12m": 30, "history.recent_break": "non", "constraints.training_days": 5,
             "sports.practiced": ["running", "strength"], "strength.sessions_per_week": 3}
    p = build_profile(facts, [], TODAY)
    ss = by_week(plan_weeks(p, date(2026, 10, 5), weeks=3))
    for w in list(ss.values())[1:]:
        days = {s.date.weekday() for s in w}
        assert len(days) in (4, 5), f"{len(days)} jours utilisés"
        assert sum(1 for s in w if s.kind.startswith("run_")) >= 3
    check_rules(p, [s for w in ss.values() for s in w])


def test_outlook_warns_when_event_is_out_of_reach():
    goal = {**EVENT, "target_date": TODAY + timedelta(weeks=12), "details": {"distance_km": 100}}
    p = build_profile({**RUDY, "running.weekly_km_8w": 2, "running.weekly_km_12m": 10}, [goal], TODAY)
    from app.plan.engine import outlook
    o = outlook(p, TODAY)
    assert o and o["ok"] is False and "repousser" in o["message"]
    easy = {**EVENT, "target_date": TODAY + timedelta(weeks=40), "details": {"distance_km": 20}}
    assert outlook(build_profile({**RUDY, "running.weekly_km_12m": 25}, [easy], TODAY), TODAY)["ok"] is True
    assert outlook(build_profile(RUDY, [], TODAY), TODAY) is None


def test_exercise_choice_follows_equipment_injuries_and_gives_start_load():
    from app.exercises.models import Exercise
    from app.plan.strength import resolve, session_plan, start_load
    from app.repo import MemoryRepo

    repo = MemoryRepo()
    names = ["Bench Press", "Barbell Full Squat", "Goblet Squat", "Reverse lunges", "Dumbbell Split Squat", "Dumbbell Bench Press", "Push-Up", "Plank"]
    repo.replace_exercises([Exercise(source="t", source_id=str(i), name=n, name_en=n, kind="strength", license="L") for i, n in enumerate(names)])
    slots = [s for s in session_plan("upper_a", False) + session_plan("lower", False) if s["pattern"] in ("h_press", "squat", "single_leg", "core")]
    facts = {"bench.bench": {"pr": {"weight": 100, "reps": 3}, "now": {"weight": 90, "reps": 5}}, "bench.squat": {"now": {"weight": 120, "reps": 5}}}
    full = {s["pattern"]: s for s in resolve(repo, slots, facts)}
    assert full["h_press"]["exercise"]["name"] == "Bench Press" and full["squat"]["exercise"]["name"] == "Barbell Full Squat"
    assert full["h_press"]["suggested_kg"] == 75.0  # 90×(1+5/30)=105 e1RM ; 105/(1+(10+2)/30)=75 (haut de la fourchette 8-10)
    home = {**facts, "constraints.equipment": ["haltères"], "history.injuries": ["genou"]}
    res = {s["pattern"]: s for s in resolve(repo, slots, home)}
    assert res["h_press"]["exercise"]["name"] == "Dumbbell Bench Press"  # pas de barre
    assert res["squat"]["exercise"]["name"] == "Goblet Squat" and "suggested_kg" not in res["squat"]  # genou : pas de squat barre
    assert res["single_leg"].get("exercise", {}).get("name") not in ("Reverse lunges", "Dumbbell Split Squat")  # genou : fentes écartées
    assert start_load("bench", {}, {"reps": "5-8"}) is None


def test_event_distance_is_read_from_the_title_when_missing():
    goal = {**EVENT, "title": "Trail 50 km", "details": {}}
    p = build_profile({**RUDY, "running.weekly_km_12m": 10}, [goal], TODAY)
    assert p.event["distance_km"] == 50
    assert build_profile(RUDY, [{**EVENT, "title": "Objectif été", "details": {}}], TODAY).event["distance_km"] == 0


def test_strength_frequency_is_never_below_what_the_watch_shows():
    base = {**RUDY, "sports.practiced": ["strength"], "strength.sessions_per_week": 1.4}
    assert build_profile(base, [], TODAY).strength_per_week == 1
    assert build_profile({**base, "strength.sessions_per_week_12m": 1.9}, [], TODAY).strength_per_week == 2
    assert build_profile({**base, "strength.sessions_per_week": 3, "strength.sessions_per_week_12m": 1.0}, [], TODAY).strength_per_week == 3


def test_tiny_running_volume_gives_three_similar_short_runs():
    facts = {**RUDY, "sports.practiced": ["running"], "running.weekly_km_8w": 12, "running.weekly_km_12m": 12, "history.recent_break": "non"}
    p = build_profile({**facts, "running.best_10k_min": 0}, [], TODAY)
    week = list(by_week(plan_weeks(p, date(2026, 10, 5), weeks=2)).values())[0]
    runs = [s.duration_min for s in week if s.kind.startswith("run_")]
    assert len(runs) == 3 and min(runs) >= 20 and max(runs) <= 2 * min(runs) + 5, runs


def test_advice_suggests_three_sessions_for_upper_body_goal():
    from app.plan.engine import advice

    p = build_profile({**RUDY, "sports.practiced": ["strength"], "strength.sessions_per_week": 1}, [], TODAY)
    assert any("3 séances" in a for a in advice(p))
    assert not advice(build_profile({**RUDY, "sports.practiced": ["strength"], "strength.sessions_per_week": 3}, [], TODAY))


def test_advice_asks_for_a_dated_event_when_missing():
    from app.plan.engine import advice

    assert any("Aucun objectif de course daté" in a for a in advice(build_profile({**RUDY, "sports.practiced": ["running"]}, [], TODAY)))
    assert not any("Aucun objectif" in a for a in advice(build_profile({**RUDY, "sports.practiced": ["running"]}, [EVENT], TODAY)))


def test_strength_blocks_vary_sets_rir_rest_and_explain():
    from app.plan.strength import session_plan

    wk = [session_plan("upper_a", False, build=b, n_build=3) for b in range(3)]
    sets = [[int(s["sets"]) for s in w] for w in wk]
    assert len({tuple(x) for x in sets}) == 3, "le volume évolue d'une semaine à l'autre"
    assert len({s for s in sets[0]}) >= 2, "séries différentes selon le rôle de l'exercice"
    rir = [wk[b][0]["rir"] for b in range(3)]
    assert rir == ["2-3", "2", "1-2"] and wk[0][0]["rpe"] == "7-8" and wk[2][0]["rpe"] == "8-9"
    de = session_plan("upper_a", False, build=0, n_build=3, deload=True)
    assert all(s["rir"] == "4" for s in de if s["role"] != "core") and de[0]["rpe"] == "6"
    assert all(s["rest"] and s["why"] and s["cue"] for s in wk[0])
    assert wk[0][0]["rest"] == "2 à 3 min" and wk[0][4]["rest"] == "1 à 1 min 30"


def test_block_progression_starts_at_the_first_generated_week():
    p = build_profile({**RUDY, "sports.practiced": ["strength"], "strength.sessions_per_week": 3}, [], TODAY)
    monday = date(2026, 10, 12)
    weeks = list(by_week(plan_weeks(p, TODAY, weeks=4, start=monday)).values())
    first = [s for s in weeks[0] if s.kind == "strength_upper"][0].details["slots"][0]
    assert first["sets"] == "4" and first["reps"] == "8-10" and first["rir"] == "2-3"  # semaine 1 du bloc : volume de départ, loin de l'échec
    assert min(s.date for w in weeks for s in w) >= monday


def test_next_target_double_progression():
    from app.plan.strength import next_target
    full = [{"kg": 60, "reps": 8}, {"kg": 60, "reps": 8}, {"kg": 65, "reps": 5}]
    assert next_target("5-8", full)["kg"] == 62.5  # séries à la charge de travail complètes -> +2,5 kg
    part = [{"kg": 40, "reps": 7}, {"kg": 40, "reps": 6}, {"kg": 30, "reps": 9}]
    t = next_target("6-10", part)
    assert t["kg"] == 40 and t["reps"] == 7
    assert next_target("6-10", [{"kg": None, "reps": 7}, {"kg": None, "reps": 6}])["reps"] == 7
    assert next_target("6-10", [{"kg": 20, "reps": None}]) is None


def test_annotate_history_uses_previous_done_session_only():
    from app.plan.strength import annotate_history
    slot = {"role": "compound", "reps": "5-8", "exercise": {"name": "Développé couché"}}
    mk = lambda i, day, status, logged=None: {"id": i, "day": day, "status": status, "logged": logged, "details": {"slots": [slot]}}  # noqa: E731
    ex = {"exercises": [{"name": "Développé couché", "sets": [{"kg": 60, "reps": 8}, {"kg": 60, "reps": 8}]}]}
    past = [mk(1, date(2026, 10, 5), "done", ex), mk(2, date(2026, 10, 12), "planned", ex)]
    out = annotate_history([mk(3, date(2026, 10, 15), "planned"), mk(1, date(2026, 10, 5), "done", ex)], past)
    assert out[0]["details"]["slots"][0]["last"]["day"] == "2026-10-05"
    assert out[0]["details"]["slots"][0]["target"]["kg"] == 62.5
    assert "last" not in out[1]["details"]["slots"][0]  # une séance ne se compare pas à elle-même
    assert "last" not in past[0]["details"]["slots"][0]  # les lignes du dépôt ne sont pas modifiées


def test_macro_phases_toward_event():
    from app.plan.cycles import macro_phase
    assert [macro_phase(n) for n in (None, 20, 12, 5, 4, 2, 1, 0)] == ["base", "base", "build", "build", "peak", "peak", "taper", "race"]


def test_cycle_continues_across_generations():
    from app.plan.cycles import continue_anchor
    p = build_profile(RUDY, [EVENT], TODAY)
    first = plan_weeks(p, TODAY, weeks=2, start=date(2026, 10, 5))
    rows = [{"day": s.date, "details": s.details} for s in first]
    anchor = continue_anchor(rows, p.deload_cycle, date(2026, 10, 19))
    assert anchor == date(2026, 10, 5)
    nxt = plan_weeks(p, TODAY, weeks=3, start=date(2026, 10, 19), anchor=anchor)
    pos = {}
    for s in nxt:
        pos[s.date - timedelta(days=s.date.weekday())] = s.details["cycle"]
    assert [pos[m]["week_in_block"] for m in sorted(pos)] == [3, 4, 1]  # la 4e semaine est la semaine allégée, puis nouveau bloc
    assert pos[date(2026, 10, 26)]["deload"] and pos[date(2026, 11, 2)]["block_no"] == 2
    # sans ancre le cycle repart de zéro : c'est exactement ce que la continuité évite
    assert plan_weeks(p, TODAY, weeks=1, start=date(2026, 10, 19))[0].details["cycle"]["week_in_block"] == 1


def test_continue_anchor_legacy_and_gap():
    from app.plan.cycles import continue_anchor
    legacy = [{"day": date(2026, 10, 7), "details": {}}, {"day": date(2026, 10, 14), "details": {}}]
    assert continue_anchor(legacy, 4, date(2026, 10, 19)) == date(2026, 10, 5)  # séances d'avant les cycles : première semaine = ancre
    assert continue_anchor(legacy, 4, date(2027, 1, 4)) is None  # longue pause : nouveau cycle
    marked = [{"day": date(2026, 10, 7), "details": {"cycle": {"anchor": "2026-09-28", "block_len": 3}}}]
    assert continue_anchor(marked, 4, date(2026, 10, 12)) is None  # longueur de bloc changée


def test_block_over_block_overload():
    from app.plan.strength import session_plan
    s1 = session_plan("upper_a", False, build=0, n_build=3, block=1)
    s2 = session_plan("upper_a", False, build=0, n_build=3, block=2)
    assert int(s2[0]["sets"]) == int(s1[0]["sets"]) + 1  # mouvement clé : une série de plus dès le 2e bloc
    assert int(s2[4]["sets"]) == int(s1[4]["sets"])  # accessoire inchangé


def test_lift_trends_orders_and_estimates():
    from app.plan.strength import lift_trends
    mk = lambda d, kg, r: {"status": "done", "day": date(2026, 10, d), "logged": {"exercises": [{"name": "Squat", "sets": [{"kg": kg, "reps": r}]}]}}  # noqa: E731
    t = lift_trends([mk(12, 65, 5), mk(5, 60, 5)])["Squat"]
    assert [x["jour"] for x in t] == ["2026-10-05", "2026-10-12"] and t[1]["e1rm"] > t[0]["e1rm"]


def _cf_profile(**kw):
    facts = {**RUDY, "sports.practiced": ["running", "strength", "crossfit"], **kw}
    return build_profile(facts, [], TODAY)


def test_crossfit_session_once_per_week_and_not_next_to_long_run():
    p = _cf_profile()
    weeks = by_week(plan_weeks(p, date(2026, 10, 5), weeks=4, start=date(2026, 10, 5)))
    for ss in weeks.values():
        cf = [s for s in ss if s.kind == "strength_crossfit"]
        assert len(cf) == 1, [s.kind for s in ss]
        for long in (s for s in ss if s.kind == "run_long"):
            assert abs((cf[0].date - long.date).days) >= 2
        assert [s.kind for s in ss].count("strength_upper") <= 1  # upper_b est remplacée


def test_crossfit_follows_cycle_and_injuries():
    from app.plan.crossfit import build
    from app.plan.cycles import cycle_for
    anchor = date(2026, 10, 5)
    fmts = [build(cycle_for(anchor + timedelta(weeks=i), anchor, 4, None), "intermédiaire", set())[1]["blocks"][2]["title"] for i in range(4)]
    assert fmts[0].startswith("WOD — AMRAP") and "tours" in fmts[1] and "EMOM" in fmts[2] and "8 min" in fmts[3]
    b2 = build(cycle_for(anchor + timedelta(weeks=4), anchor, 4, None), "intermédiaire", set())
    assert "AMRAP 14" in b2[1]["blocks"][2]["title"]  # bloc 2 : WOD plus long
    text = str(build(cycle_for(anchor + timedelta(weeks=1), anchor, 4, None), "intermédiaire", {"genou", "épaule"})[1])
    assert "burpees" not in text.lower() and "wall balls" not in text.lower() and "thruster" not in text.lower()


def test_no_crossfit_without_declared_sport_or_near_event():
    assert not any(s.kind == "strength_crossfit" for s in plan_weeks(build_profile(RUDY, [], TODAY), TODAY, weeks=4))
    near = {**EVENT, "target_date": date(2026, 11, 14)}
    p = build_profile({**RUDY, "sports.practiced": ["running", "strength", "crossfit"]}, [near], TODAY)
    assert not any(s.kind == "strength_crossfit" for s in plan_weeks(p, TODAY, weeks=4))


def test_describe_projects_cycle_from_one_generated_week():
    from app.plan.cycles import cycle_for, describe
    anchor = date(2026, 10, 5)
    one = [{"day": date(2026, 10, 14), "details": {"cycle": cycle_for(date(2026, 10, 12), anchor, 4, None).as_dict()}}]
    d = describe(one, date(2026, 10, 14))
    assert d["current"]["week_in_block"] == 2 and len(d["upcoming"]) == 8  # le futur est calculé, pas lu en base
    assert d["next_deload"] == "2026-10-26" and d["upcoming"][4]["bloc"] == 2


def test_event_driven_long_run_builds_toward_the_race():
    from app.plan.engine import event_long_peak, event_long_run
    ev = {"status": "active", "kind": "event", "target_date": date(2026, 12, 6), "priority": "principal", "title": "Trail 16 km",
          "details": {"distance_km": 16, "elevation_m": 370}}
    facts = {**RUDY, "sports.practiced": ["trail", "running", "strength"], "running.weekly_km_8w": 1.9, "running.longest_recent_min": 35,
             "constraints.training_days": 5, "multisport.blocked_days": ["dimanche"]}
    facts.pop("running.best_10k_min", None)
    p = build_profile(facts, [ev], date(2026, 10, 13))
    sessions = plan_weeks(p, date(2026, 10, 13), weeks=8, start=date(2026, 10, 12))
    longs = {s.date: s for s in sessions if s.kind == "run_long"}
    mins = [longs[d].duration_min for d in sorted(longs)]
    peak = event_long_peak(p)
    assert 80 <= peak <= 110 and max(mins) == peak and mins[0] == 45 and mins[1] > mins[0]  # part de la dernière sortie réelle (35 min) + 10
    assert mins[-2] < peak and mins[-1] <= 30  # affûtage puis veille de course
    deload = [s for s in longs.values() if s.details["cycle"]["deload"]]
    assert deload and all(s.duration_min < peak for s in deload)
    assert all(s.details["vert_m"] <= 370 * 0.8 + 10 for s in longs.values() if "vert_m" in s.details)
    assert "C9" in longs[min(longs)].rules
    # stateless : si la sortie n'est pas faite, la génération suivante ne s'emballe pas
    assert event_long_run(p, 6, 0) == 45
    # hors fenêtre de 12 semaines ou sans objectif : comportement habituel
    assert event_long_run(p, 20, 0) is None and event_long_run(build_profile(RUDY, [], date(2026, 10, 13)), 6, 0) is None


def test_short_event_keeps_chosen_strength_frequency_but_legs_stay_in_maintenance():
    short = {**EVENT, "target_date": TODAY + timedelta(days=49), "details": {"distance_km": 16}}
    p = build_profile({**RUDY, "sports.practiced": ["running", "strength"], "strength.sessions_per_week": 3}, [short], TODAY)
    week = list(by_week(plan_weeks(p, TODAY, weeks=2, start=date(2026, 10, 12))).values())[0]
    assert sum(1 for s in week if s.kind.startswith("strength")) == 3
    assert all("entretien" in s.title for s in week if s.kind == "strength_lower")


def test_at_least_three_runs_per_week_with_four_days_or_more():
    f = {**RUDY, "sports.practiced": ["running"], "running.weekly_km_8w": 4, "running.weekly_km_12m": 6, "constraints.training_days": 5,
         "history.recent_break": "non", "running.weeks_since_last_run": 0}
    for w in list(by_week(plan_weeks(build_profile(f, [], TODAY), date(2026, 10, 5), weeks=4)).values())[1:]:
        assert sum(1 for s in w if s.kind.startswith("run_")) >= 3, [(s.date.strftime("%a"), s.kind) for s in w]


def test_plan_can_be_read_one_week_at_a_time_with_bounds():
    from fastapi.testclient import TestClient

    from app.auth import reset_rate_limits
    from app.main import app, get_repo
    from app.repo import MemoryRepo

    reset_rate_limits()
    repo = MemoryRepo()
    app.dependency_overrides[get_repo] = lambda: repo
    try:
        c = TestClient(app)
        uid = c.post("/auth/register", json={"name": "R", "email": "wk@example.org", "password": "un-mot-de-passe-solide"}).json()["id"]
        c.post(f"/users/{uid}/answers", json={"question_id": "goal.sports", "value": ["running", "strength"]})
        c.post(f"/users/{uid}/answers", json={"question_id": "con.days", "value": 4})
        monday = TODAY - timedelta(days=TODAY.weekday())
        repo.add_sessions(uid, [{"day": monday - timedelta(days=14), "kind": "run_easy", "title": "Ancienne", "duration_min": 30, "details": {},
                                 "rules": ["C1"], "notes": []}])
        c.post(f"/users/{uid}/plan/generate", json={"weeks": 3})
        old = c.get(f"/users/{uid}/plan?week={monday - timedelta(days=14)}").json()
        assert [s["title"] for s in old["sessions"]] == ["Ancienne"]  # une semaine passée reste consultable
        cur = c.get(f"/users/{uid}/plan").json()
        assert cur["bounds"]["first"] == (monday - timedelta(days=14)).isoformat() and cur["bounds"]["last"] > cur["today"]
        nxt = c.get(f"/users/{uid}/plan?week={monday + timedelta(days=7)}").json()
        assert all(monday + timedelta(days=7) <= date.fromisoformat(s["day"]) < monday + timedelta(days=14) for s in nxt["sessions"])
    finally:
        app.dependency_overrides.clear()


def test_week_view_lists_unplanned_garmin_activities_and_extends_bounds():
    from fastapi.testclient import TestClient

    from app.auth import reset_rate_limits
    from app.main import app, get_repo
    from app.repo import MemoryRepo

    reset_rate_limits()
    repo = MemoryRepo()
    app.dependency_overrides[get_repo] = lambda: repo
    try:
        c = TestClient(app)
        uid = c.post("/auth/register", json={"name": "R", "email": "wa@example.org", "password": "un-mot-de-passe-solide"}).json()["id"]
        old = TODAY - timedelta(days=100)
        repo.upsert_activities(uid, [{"garmin_id": "9", "day": old, "started_at": __import__("datetime").datetime(old.year, old.month, old.day, 8), "sport": "run",
                                      "type_key": "running", "name": "Sortie ancienne", "duration_s": 3000, "distance_m": 8000.0, "elevation_m": 10.0,
                                      "avg_hr": 150, "max_hr": 170, "calories": 500, "training_load": 50.0}])
        w = c.get(f"/users/{uid}/plan?week={old}").json()
        assert [a["name"] for a in w["activities"]] == ["Sortie ancienne"] and w["bounds"]["first"] == old.isoformat()
        assert c.get(f"/users/{uid}/plan").json()["bounds"]["first"] == old.isoformat()  # on peut remonter jusqu'à l'historique Garmin
    finally:
        app.dependency_overrides.clear()


def test_pain_written_in_free_text_is_detected_and_steers_exercise_choice():
    from app.exercises.models import Exercise
    from app.plan.pain import pain_zones
    from app.plan.strength import resolve, session_plan
    from app.repo import MemoryRepo

    s = [{"day": TODAY - timedelta(days=3), "logged": {"note": "Douleurs coude gauche depuis 2 semaines"}},
         {"day": TODAY - timedelta(days=2), "logged": {"note": "Séance facile, pas de souci", "adaptation": "Genou ok"}},
         {"day": TODAY - timedelta(days=60), "logged": {"note": "mal à l'épaule"}}]
    assert pain_zones(s, TODAY) == {"coude"}  # ni « genou ok » ni une douleur vieille de deux mois
    repo = MemoryRepo()
    names = ["Triceps Pushdown", "Dips", "Push-Up", "Bench Dips"]
    repo.replace_exercises([Exercise(source="t", source_id=str(i), name=n, name_en=n, kind="strength", license="L") for i, n in enumerate(names)])
    slot = [x for x in session_plan("upper_a", False) if x["pattern"] == "triceps"]
    assert resolve(repo, slot, {})[0]["exercise"]["name"] == "Triceps Pushdown"
    assert resolve(repo, slot, {"history.injuries": ["coude"]}) == []  # coude douloureux : l'isolation du triceps disparaît de la séance


def test_named_exercises_can_be_avoided_without_dropping_the_whole_zone():
    from app.exercises.models import Exercise
    from app.plan.strength import resolve, session_plan
    from app.repo import MemoryRepo

    repo = MemoryRepo()
    names = ["Pull-ups", "Wide-Grip Lat Pulldown", "Dumbbell Bicep Curl"]
    repo.replace_exercises([Exercise(source="t", source_id=str(i), name=n, name_en=n, kind="strength", license="L") for i, n in enumerate(names)])
    slots = [x for x in session_plan("upper_b", False) if x["pattern"] in ("v_pull", "biceps")]
    assert {s["pattern"]: s["exercise"]["name"] for s in resolve(repo, slots, {})} == {"v_pull": "Pull-ups", "biceps": "Dumbbell Bicep Curl"}
    res = {s["pattern"]: s["exercise"]["name"] for s in resolve(repo, slots, {"history.avoid_exercises": ["Pull-up", " "]})}
    assert res == {"v_pull": "Wide-Grip Lat Pulldown", "biceps": "Dumbbell Bicep Curl"}  # les tractions seules sont écartées, pas les curls
