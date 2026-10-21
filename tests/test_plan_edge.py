"""Cas limites du moteur de plan et de l'API de génération (ticket #26) : semaine terminée, week-end, jours bloqués, blessure en texte libre,
reprise après arrêt, entrées absurdes ou manquantes. Les propriétés (G1, G5, C2, C8, S1, S2) sont vérifiées en itérant sur des dates et des profils.

Les règles S3 à S6 (perte de poids, mineur, trouble alimentaire) relèvent du moteur de nutrition : voir tests/test_nutrition.py.
"""
import math
from datetime import date, timedelta
from itertools import product

import pytest
from fastapi.testclient import TestClient

import app.plan.api as plan_api
from app.auth import reset_rate_limits
from app.main import app, get_repo
from app.plan import engine as E
from app.plan.engine import DAYS, KEY, Profile, advice, build_profile, empty_reason, outlook, plan_weeks, warnings
from app.plan.injuries import normalize_injuries, zones_in_text
from app.questionnaire.models import Fact
from app.repo import MemoryRepo
from tests.test_plan import EVENT, RUDY, by_week, check_rules, run_minutes

MONDAY = date(2026, 10, 12)
BASE = {
    "constraints.weekday_session_max_min": 75, "constraints.weekend_session_max_min": 180, "running.weekly_km_8w": 30, "running.best_10k_min": 50,
    "strength.sessions_per_week": 3, "strength.level": "intermédiaire", "body.birth_year": 1995, "history.recent_break": "non", "history.injuries": ["aucune"],
}
SPORTS = [["running"], ["running", "strength"], ["running", "strength", "crossfit"], ["running", "strength", "hyrox"], ["strength"], ["crossfit"], ["hyrox"], ["trail", "strength"]]
BLOCKS = [[], ["vendredi"], ["samedi", "dimanche"], ["mardi", "jeudi", "samedi"], DAYS[:5], DAYS[2:]]
DAYS_PER_WEEK = [2, 4, 6]


def profiles():
    for sports, blocked, n in product(SPORTS, BLOCKS, DAYS_PER_WEEK):
        yield {**BASE, "sports.practiced": sports, "multisport.blocked_days": blocked, "constraints.training_days": n}


def full_weeks(facts, goals=(), offset=0, weeks=4, today=MONDAY):
    """Plan de semaines entières (démarrage un lundi) ; `offset` décale la position dans le bloc 3+1."""
    p = build_profile(facts, list(goals), today)
    return p, plan_weeks(p, today, weeks, start=today, anchor=today - timedelta(weeks=offset))


def start_dates(n=14):
    return [MONDAY + timedelta(days=i) for i in range(n)]  # deux semaines : tous les jours de la semaine, deux fois


# ---------- propriétés : toutes les dates, tous les profils ----------
def test_g5_g6_c1_c2_hold_for_every_start_day_and_profile():
    for facts in profiles():
        for today in start_dates(7):
            p = build_profile(facts, [], today)
            sessions = plan_weeks(p, today, weeks=3, start=today)
            check_rules(p, [s for s in sessions if s.date >= today - timedelta(days=today.weekday()) + timedelta(days=7)])  # semaines entières : la première est entamée
            keys = sorted(s.date for s in sessions if s.kind in KEY)
            assert all((b - a).days >= 2 for a, b in zip(keys, keys[1:], strict=False)), f"G5 : deux séances clés à moins de 48 h ({facts['sports.practiced']}, {today})"
            assert all(s.date >= today for s in sessions)
            assert all(sum(1 for s in ss if s.kind == "run_long") <= 1 for ss in by_week(sessions).values()), "C2 : une sortie longue par semaine"
            assert all(s.duration_min <= 150 for s in sessions if s.kind == "run_long"), "C2 : sortie longue ≤ 2 h 30"


def test_g1_weekly_run_volume_never_jumps_more_than_ten_percent():
    checked = 0
    for facts in profiles():
        if not any(s in facts["sports.practiced"] for s in ("running", "trail")):
            continue
        for offset in range(4):  # chaque position possible dans le bloc 3+1
            _, sessions = full_weeks(facts, offset=offset, weeks=6)
            last_build = None
            for ss in by_week(sessions).values():
                cyc = ss[0].details["cycle"]
                vol = run_load(ss)
                if cyc["deload"] or cyc["macro"] == "taper":
                    continue
                if last_build and vol:
                    assert vol <= last_build * 1.10 + 12, f"G1 : {last_build} -> {vol} min ({facts['sports.practiced']}, décalage {offset})"
                    checked += 1
                last_build = vol or last_build
    assert checked > 500


@pytest.mark.parametrize("days_before", range(0, 15))
def test_event_less_than_two_weeks_away_keeps_the_event_day_clear_and_never_raises(days_before):
    ev = {**EVENT, "target_date": MONDAY + timedelta(days=days_before), "title": "10 km", "details": {"distance_km": 10}}
    for facts in list(profiles())[::7]:
        p = build_profile(facts, [ev], MONDAY)
        sessions = plan_weeks(p, MONDAY, weeks=3, start=MONDAY)
        assert not [s for s in sessions if s.date == ev["target_date"]], "C6 : le jour de l'événement est la séance"
        assert not [s for s in sessions if s.kind.startswith("run_") and ev["target_date"] < s.date <= ev["target_date"] + timedelta(days=2)]
        assert outlook(p, MONDAY) is None or outlook(p, MONDAY)["weeks_to_event"] >= 0
        for ss in by_week(sessions).values():  # C9 dépasse volontairement C2 près de l'objectif : on ne vérifie ici que les jours bloqués, C1 et le jour de repos
            assert not {s.date.weekday() for s in ss} & p.blocked and len({s.date for s in ss}) <= 6
            assert sum(1 for s in ss if s.kind == "run_quality") <= 1


def test_s1_red_flags_give_no_plan_whatever_the_day_and_profile():
    for facts in list(profiles())[::5]:
        for today in start_dates(7):
            blocked = {**facts, "health.red_flags": ["douleur thoracique"], "health.red_flags_discussed": "non"}
            p = build_profile(blocked, [], today)
            assert plan_weeks(p, today, weeks=2, start=today) == []
            assert "médecin" in empty_reason(p)
    ok = build_profile({**RUDY, "health.red_flags": ["douleur thoracique"], "health.red_flags_discussed": "oui"}, [], MONDAY)
    assert plan_weeks(ok, MONDAY, weeks=1, start=MONDAY)


@pytest.mark.parametrize("injury", ["genou", "Cheville", "tendinite d'Achille", "shin splints", "hamstring pull", "plantar fasciitis", "mollets"])
def test_s2_running_injury_freezes_volume_and_intensity_for_every_profile(injury):
    for facts in profiles():
        if not any(s in facts["sports.practiced"] for s in ("running", "trail")):
            continue
        p, sessions = full_weeks({**facts, "history.injuries": [injury]}, weeks=4)
        assert p.run_injury, injury
        vols = [run_minutes(ss) for ss in by_week(sessions).values() if not ss[0].details["cycle"]["deload"]]
        assert all(b <= a for a, b in zip(vols, vols[1:], strict=False) if b), f"S2 : le volume monte malgré la douleur ({vols})"
        assert not [s for s in sessions if s.kind == "run_quality"], "S2 : pas d'intensité de course"


def test_c8_very_long_runs_are_never_closer_than_ten_days():
    ev = {**EVENT, "target_date": MONDAY + timedelta(weeks=14)}
    p = build_profile({**RUDY, "constraints.weekend_session_max_min": 360}, [ev], MONDAY)
    longs = [s for s in plan_weeks(p, MONDAY, weeks=12, start=MONDAY) if s.kind == "run_long" and s.duration_min > 180]
    assert all((b.date - a.date).days >= 10 for a, b in zip(longs, longs[1:], strict=False))


# ---------- (2) week-ends et jours bloqués : dégrader et le dire ----------
def hybrid_weeks(facts):
    p, sessions = full_weeks(facts, weeks=4)
    return p, list(by_week(sessions).values())[1:]  # la première semaine est écartée


def test_a_hybrid_session_that_cannot_be_placed_is_announced_not_dropped_silently():
    seen = 0
    for sports, blocked, n in product([["running", "strength", "hyrox"], ["running", "strength", "crossfit"], ["running", "hyrox"]], BLOCKS, [3, 4, 5, 6]):
        facts = {**BASE, "sports.practiced": sports, "multisport.blocked_days": blocked, "constraints.training_days": n}
        _, weeks = hybrid_weeks(facts)
        for ss in weeks:
            if any(s.kind == "strength_crossfit" for s in ss):
                continue
            seen += 1
            assert any("conditionnement" in note or "CrossFit" in note for s in ss for note in s.notes), f"séance hybride perdue sans avertissement : {sports} {blocked} {n}"
    assert seen > 50  # le cas existe bel et bien : la propriété n'est pas vide


def test_run_strength_and_hyrox_week_says_what_it_dropped():
    facts = {**BASE, "sports.practiced": ["running", "strength", "hyrox"], "constraints.training_days": 4, "multisport.blocked_days": ["vendredi"]}
    _, weeks = hybrid_weeks(facts)
    notes = {n for ss in weeks for s in ss for n in s.notes}
    assert any("n'a pas pu être placée" in n and "G5" in n for n in notes)


def test_every_wanted_session_is_placed_or_announced():
    """Sortie longue voulue mais absente = note (G9)."""
    for facts in profiles():
        sports = facts["sports.practiced"]
        p, sessions = full_weeks(facts, weeks=3)
        for ss in list(by_week(sessions).values())[1:]:
            kinds = [s.kind for s in ss]
            notes = " ".join(n for s in ss for n in s.notes)
            if p.runs and not p.dedicated and "run_long" not in kinds:
                assert "sortie longue n'a pas pu être placée" in notes, (sports, facts["multisport.blocked_days"], facts["constraints.training_days"])


def test_blocked_days_leaving_fewer_than_three_sessions_are_explained():
    facts = {**BASE, "sports.practiced": ["running", "strength"], "multisport.blocked_days": DAYS[:5], "constraints.training_days": 5}
    p = build_profile(facts, [], MONDAY)
    sessions = plan_weeks(p, MONDAY, weeks=2, start=MONDAY)
    assert sessions and {s.date.weekday() for s in sessions} <= {5, 6} and len({s.date for s in by_week(sessions)[MONDAY]}) <= 1  # G5 : un jour de repos
    text = " ".join(warnings(p))
    assert "5 jours" in text and "moins de 3 séances" in text


def test_all_days_blocked_gives_a_clear_reason_not_a_missing_sport_message():
    p = build_profile({**RUDY, "multisport.blocked_days": DAYS}, [], MONDAY)
    assert plan_weeks(p, MONDAY, weeks=2, start=MONDAY) == []
    assert "jours bloqués" in empty_reason(p) and "sports" not in empty_reason(p)
    one_day = build_profile({**RUDY, "multisport.blocked_days": DAYS[:6]}, [], MONDAY)
    assert plan_weeks(one_day, MONDAY, weeks=1, start=MONDAY) == [] and "jours bloqués" in empty_reason(one_day)


def test_session_durations_respect_the_declared_maximum_g6():
    for sports, wd, we in product(SPORTS, (30, 45, 60, 90), (30, 60, 120)):
        facts = {**BASE, "sports.practiced": sports, "constraints.weekday_session_max_min": wd, "constraints.weekend_session_max_min": we, "constraints.training_days": 5}
        p = build_profile(facts, [], MONDAY)
        for s in plan_weeks(p, MONDAY, weeks=3, start=MONDAY):
            cap = we if s.date.weekday() >= 5 else wd
            limit = cap * E.CAP_TOLERANCE if s.kind.startswith("strength_") and s.kind != "strength_crossfit" else cap
            assert s.duration_min <= limit, f"G6 : {s.kind} {s.duration_min} min > {cap} ({sports}, {wd}/{we})"


def test_a_short_declared_maximum_trims_accessories_and_says_so():
    p = build_profile({**RUDY, "sports.practiced": ["strength"], "constraints.weekday_session_max_min": 45, "constraints.training_days": 3}, [], MONDAY)
    sessions = [s for s in plan_weeks(p, MONDAY, weeks=1, start=MONDAY) if s.kind.startswith("strength")]
    assert sessions
    for s in sessions:
        roles = [sl["role"] for sl in s.details["slots"]]
        assert roles[0] == "compound" and s.duration_min <= 45 * E.CAP_TOLERANCE
        assert any("raccourcie" in n for n in s.notes)


# ---------- (1) semaine terminée, génération en fin de semaine ----------
class _Env:
    def __init__(self, monkeypatch):
        self.monkeypatch = monkeypatch
        self.repo = MemoryRepo()
        app.dependency_overrides[get_repo] = lambda: self.repo
        reset_rate_limits()
        self.client = TestClient(app)
        self.uid = self.client.post("/auth/register", json={"name": "R", "email": "edge@example.org", "password": "un-mot-de-passe-solide"}).json()["id"]

    def facts(self, **kw):
        self.repo.add_facts(self.uid, [Fact(key=k.replace("__", "."), value=v, source="test") for k, v in kw.items()])

    def generate(self, today, **body):
        class FakeDate(date):
            @classmethod
            def today(cls):
                return today

        self.monkeypatch.setattr(plan_api, "date", FakeDate)
        return self.client.post(f"/users/{self.uid}/plan/generate", json=body).json()


@pytest.fixture
def env(monkeypatch):
    e = _Env(monkeypatch)
    yield e
    app.dependency_overrides.clear()


def test_generation_on_any_weekday_never_leaves_an_empty_plan(env):
    env.facts(**{"sports__practiced": ["running", "strength"], "constraints__training_days": 4, "multisport__blocked_days": ["samedi", "dimanche"]})
    for today in start_dates(7):
        r = env.generate(today)
        assert r["created"] > 0 and r["reason"] is None, f"{today:%A} : plan vide ({r})"  # le vendredi, il ne reste que des jours bloqués : on prépare la semaine suivante
        assert date.fromisoformat(r["from"]) >= today
        rows = env.repo.list_sessions(env.uid, today, None)
        assert all(r_["day"] >= today for r_ in rows)
        assert not {r_["day"].weekday() for r_ in rows} & {5, 6}


def test_weekend_generation_prepares_next_week_and_finished_week_does_not_replan_the_past(env):
    env.facts(**{"sports__practiced": ["running"], "constraints__training_days": 3})
    sunday = MONDAY + timedelta(days=6)
    assert env.generate(sunday)["from"] == (MONDAY + timedelta(days=7)).isoformat()
    # semaine terminée : des séances existent déjà cette semaine, tout est passé -> la génération part de lundi prochain
    env.repo.add_sessions(env.uid, [{"day": MONDAY, "kind": "run_easy", "title": "Footing facile", "duration_min": 40, "details": {}, "rules": ["C1"], "notes": []}])
    r = env.generate(sunday)
    assert r["from"] == (MONDAY + timedelta(days=7)).isoformat() and r["created"] > 0
    assert any(s["day"] == MONDAY for s in env.repo.list_sessions(env.uid, MONDAY, MONDAY + timedelta(days=1))), "la semaine terminée n'est pas touchée"


def test_the_event_day_can_be_today_and_the_plan_stays_clear_of_it(env):
    env.facts(**{"sports__practiced": ["running", "strength"], "constraints__training_days": 4})
    env.repo.create_goal(env.uid, {"title": "10 km", "kind": "event", "target_date": MONDAY, "priority": "principal", "details": {"distance_km": 10}})
    r = env.generate(MONDAY)
    assert r["reason"] is None
    assert not env.repo.list_sessions(env.uid, MONDAY, MONDAY)


def test_empty_plan_reasons_are_specific(env):
    assert "sports" in env.generate(MONDAY)["reason"]
    env.facts(**{"sports__practiced": ["running"], "constraints__training_days": 0})
    r = env.generate(MONDAY)
    assert r["created"] == 0 and "0 jour" in r["reason"] and any("0 jour" in w for w in r["warnings"])
    env.facts(**{"constraints__training_days": 3, "multisport__blocked_days": DAYS})
    assert "jours bloqués" in env.generate(MONDAY)["reason"]


# ---------- (3) blessure en texte libre ----------
@pytest.mark.parametrize("text,zone", [
    ("Genoux", "genou"), ("genou gauche", "genou"), ("knee pain", "genou"), ("Douleur au GENOU", "genou"), ("tendinite rotulienne", "genou"),
    ("Épaules", "épaule"), ("epaule droite", "épaule"), ("my shoulder", "épaule"), ("tendinite d'Achille", "tendon d'Achille"), ("Achilles tendon", "tendon d'Achille"),
    ("tendon d’Achille", "tendon d'Achille"), ("périostite", "tibia"), ("shin splints", "tibia"), ("mollets", "mollet"), ("calf strain", "mollet"),
    ("fasciite plantaire", "pied"), ("plantar fasciitis", "pied"), ("ischios", "ischio-jambiers"), ("hamstrings", "ischio-jambiers"), ("lombalgie", "dos"),
    ("lower back", "dos"), ("Hanches", "hanche"), ("hip", "hanche"), ("coudes", "coude"), ("tennis elbow", "coude"), ("poignets", "poignet"), ("chevilles", "cheville"),
])
def test_free_text_injuries_are_normalised_to_known_zones(text, zone):
    assert zones_in_text(text) == {zone}
    for facts in ({"history.injuries": [text]}, {"history.injuries": ["autre"], "history.injuries.other": text}, {"history.injuries": ["aucune"], "history.injury_detail": text},
                  {"history.injuries": text}):
        zones, unknown = normalize_injuries(facts)
        assert zones == {zone} and not unknown
        assert build_profile({**RUDY, **facts}, [], MONDAY).injuries == {zone}


@pytest.mark.parametrize("value", ["aucune", "Aucune", "none", "No", "non", "rien", "RAS", "pas de blessure", "Pas de douleur au genou", "no injuries", "", "   ", "autre"])
def test_no_injury_wordings_give_no_injury(value):
    assert normalize_injuries({"history.injuries": [value]}) == (set(), [])
    assert not build_profile({**RUDY, "history.injuries": [value]}, [], MONDAY).run_injury


def test_unrecognised_injury_text_is_kept_and_announced_never_ignored():
    facts = {**RUDY, "history.injuries": ["autre"], "history.injuries.other": "élongation du quadriceps"}
    zones, unknown = normalize_injuries(facts)
    assert zones == set() and unknown == ["élongation du quadriceps"]
    p = build_profile(facts, [], MONDAY)
    sessions = plan_weeks(p, MONDAY, weeks=1, start=MONDAY)
    assert sessions and all(any("quadriceps" in n and "S7" in n for n in s.notes) for s in sessions)
    assert any("quadriceps" in w for w in warnings(p))
    assert not p.run_injury and not p.injuries


@pytest.mark.parametrize("value", [None, 0, 1.5, True, float("nan"), float("inf"), 10**400, {}, {"a": 1}, [[1]], [None, 3, {"x": 1}], ["x" * 5000], "é" * 400, [""], "\x00genou\x00"])
def test_garbage_injury_values_never_raise(value):
    for key in ("history.injuries", "history.injuries.other", "history.injury_detail"):
        p = build_profile({**RUDY, key: value}, [], MONDAY)
        assert plan_weeks(p, MONDAY, weeks=1, start=MONDAY) is not None
        advice(p)


def test_injury_written_as_other_steers_exercise_choice_end_to_end(env):
    from app.exercises.models import Exercise

    env.repo.replace_exercises([Exercise(source="t", source_id=str(i), name=n, name_en=n, kind="strength", muscles_primary=["chest"], equipment=["barbell"], license="L")
                                for i, n in enumerate(["Bench Press", "Barbell Full Squat", "Goblet Squat", "Dumbbell Split Squat", "Reverse lunges", "Romanian Deadlift", "Plank",
                                                       "Pull-ups", "Seated Cable Row", "Standing Military Press", "Side Lateral Raise"])])
    env.facts(**{"sports__practiced": ["strength"], "constraints__training_days": 3, "history__injuries": ["autre"], "history__injuries__other": "Mes GENOUX me font mal"})
    env.generate(MONDAY + timedelta(days=5), weeks=2)
    names = [sl["exercise"]["name"].lower() for s in env.repo.list_sessions(env.uid, MONDAY, None) if s["kind"] == "strength_lower" for sl in s["details"]["slots"] if "exercise" in sl]
    assert names and not any(x in n for n in names for x in ("lunge", "split squat", "full squat"))


def test_pain_in_session_feedback_is_read_in_english_with_plurals_and_accents():
    from app.plan.pain import pain_zones

    log = lambda note: [{"day": MONDAY, "logged": {"note": note}}]  # noqa: E731
    assert pain_zones(log("Pain in both knees"), MONDAY) == {"genou"}
    assert pain_zones(log("douleur aux Épaules et aux mollets"), MONDAY) == {"épaule", "mollet"}
    assert pain_zones(log("tout va bien, genou parfait"), MONDAY) == set()


# ---------- (4) reprise après arrêt ----------
def run_load(ss):
    """Minutes de course d'une semaine, y compris celles des séances hybrides."""
    return E._run_total(ss)


def km_to_min(km, p):
    return km * p.easy_pace


@pytest.mark.parametrize("weeks_off,km8,km12", [(12, 0, 0), (99, 30, 30), (8, 30, 0), (6, 0, 40), (20, 5, 60), (5, 30, 30)])
def test_long_break_restarts_at_a_fraction_of_the_usual_volume_and_climbs_gently(weeks_off, km8, km12):
    facts = {**BASE, "sports.practiced": ["running"], "running.weeks_since_last_run": weeks_off, "running.weekly_km_8w": km8, "running.weekly_km_12m": km12, "constraints.training_days": 4}
    p, sessions = full_weeks(facts, weeks=8)
    usual = max(km_to_min(km8, p), km_to_min(km12, p)) or km_to_min(12, p)
    vols = [run_minutes(ss) for ss in by_week(sessions).values()]
    assert vols[0] <= max(0.3 * usual + 20, 75), f"G8 : reprise trop forte ({vols[0]} min pour un volume habituel de {usual:.0f})"
    last_build = None
    for ss in by_week(sessions).values():
        cyc = ss[0].details["cycle"]
        v = run_minutes(ss)
        assert v <= usual * 1.1 + 5 or last_build and v <= last_build * 1.10 + 1, f"la reprise dépasse le volume d'avant l'arrêt ({v} > {usual:.0f})"
        if not cyc["deload"]:
            if last_build:
                assert v <= last_build * (E.RETURN_GROWTH_MAX + 0.03), f"G3 : montée de {last_build} à {v} min"
            last_build = v


def test_break_without_any_history_does_not_start_at_the_default_twelve_kilometres():
    base = {**BASE, "sports.practiced": ["running"], "running.weekly_km_8w": 0, "constraints.training_days": 3}
    default = full_weeks(base, weeks=1)[1]
    after = full_weeks({**base, "running.weeks_since_last_run": 12}, weeks=1)[1]
    assert run_minutes(after) <= 0.8 * run_minutes(default)


def test_return_ramp_never_overshoots_the_pre_break_volume():
    facts = {**BASE, "sports.practiced": ["running"], "running.weeks_since_last_run": 9, "running.weekly_km_8w": 0, "running.weekly_km_12m": 30, "constraints.training_days": 4}
    p = build_profile(facts, [], MONDAY)
    usual = 30 * p.easy_pace
    vols = [v for v, deload, _ in E.weekly_volumes(p, 12, None) if not deload]
    assert vols[0] <= 0.4 * usual and max(vols[:6]) <= usual + 1
    assert all(b <= a * 1.15 + 1 for a, b in zip(vols, vols[1:], strict=False))


def test_after_break_flag_with_a_long_gap_since_last_session_still_plans(env):
    env.facts(**{"sports__practiced": ["running", "strength"], "constraints__training_days": 4, "history__recent_break": "oui blessure", "running__weeks_since_last_run": 10})
    old = MONDAY - timedelta(weeks=14)
    env.repo.add_sessions(env.uid, [{"day": old, "kind": "run_easy", "title": "Footing facile", "duration_min": 40, "details": {"cycle": {"anchor": old.isoformat(), "block_len": 4}},
                                     "rules": ["C1"], "notes": []}])
    r = env.generate(MONDAY)
    assert r["created"] > 0
    first = min(env.repo.list_sessions(env.uid, MONDAY, None), key=lambda s: s["day"])
    assert first["details"]["cycle"]["block_no"] == 1  # une pause de plus de 8 semaines : nouveau cycle (G7)


def test_a_returning_runner_gets_the_return_advice_and_a_light_hybrid_start():
    facts = {**BASE, "sports.practiced": ["running", "hyrox"], "running.weeks_since_last_run": 10, "history.recent_break": "oui blessure"}
    p = build_profile(facts, [], MONDAY)
    assert any("Reprise de la course" in a for a in advice(p))
    first = by_week(plan_weeks(p, MONDAY, weeks=2, start=MONDAY))[MONDAY]
    assert not [s for s in first if s.kind == "run_quality"]


# ---------- (5) entrées absurdes ou manquantes ----------
@pytest.mark.parametrize("days,expected", [(0, None), (1, 2), (2, 2), (6, 6), (7, 6), (8, 6), (99, 6), (3.7, 3)])
def test_training_days_out_of_range_are_clamped_with_a_message(days, expected):
    p = build_profile({**RUDY, "constraints.training_days": days}, [], MONDAY)
    sessions = plan_weeks(p, MONDAY, weeks=1, start=MONDAY)
    if expected is None:
        assert sessions == [] and p.no_days and any("0 jour" in w for w in warnings(p))
        return
    assert p.days_per_week == expected and sessions
    assert len({s.date for s in sessions}) <= 6
    if days in (0, 1, 7, 8, 99):
        assert warnings(p)


@pytest.mark.parametrize("key,value", [("constraints.weekday_session_max_min", 0), ("constraints.weekday_session_max_min", -30), ("constraints.weekday_session_max_min", "une heure"),
                                       ("constraints.weekday_session_max_min", 5), ("constraints.weekend_session_max_min", 0), ("constraints.weekday_session_max_min", 10**9)])
def test_absurd_durations_fall_back_with_a_message_and_a_usable_plan(key, value):
    p = build_profile({**RUDY, key: value}, [], MONDAY)
    sessions = plan_weeks(p, MONDAY, weeks=2, start=MONDAY)
    assert sessions and all(s.duration_min > 0 for s in sessions)
    assert E.MIN_SESSION_MIN <= p.weekday_max <= E.MAX_SESSION_MIN and E.MIN_SESSION_MIN <= p.weekend_max <= E.MAX_SESSION_MIN
    if value != 10**9:
        assert warnings(p)


def test_past_event_is_ignored_with_a_message_and_today_event_is_kept():
    past = {**EVENT, "target_date": MONDAY - timedelta(days=10), "title": "Semi de Lyon"}
    p = build_profile(RUDY, [past], MONDAY)
    assert p.event is None and any("Semi de Lyon" in w and "passée" in w for w in warnings(p))
    assert plan_weeks(p, MONDAY, weeks=2, start=MONDAY)
    assert outlook(p, MONDAY) is None
    assert build_profile(RUDY, [{**EVENT, "target_date": MONDAY}], MONDAY).event["date"] == MONDAY
    assert not warnings(build_profile(RUDY, [{**past, "target_date": MONDAY - timedelta(days=400)}], MONDAY))  # un vieil objectif oublié ne réclame pas d'attention


def test_two_goals_on_the_same_day_are_resolved_deterministically_and_announced():
    a = {**EVENT, "title": "Trail A 30 km", "priority": "important", "details": {"distance_km": 30}}
    b = {**EVENT, "title": "Trail B 20 km", "priority": "principal", "details": {"distance_km": 20}}
    c = {**EVENT, "title": "Trail C 20 km", "priority": "principal", "details": {"distance_km": 20}}
    first = build_profile(RUDY, [a, b, c], MONDAY)
    assert first.event["title"] == "Trail B 20 km" and first.event == build_profile(RUDY, [c, b, a], MONDAY).event
    assert any("même jour" in w and "Trail B 20 km" in w for w in warnings(first))
    assert plan_weeks(first, MONDAY, weeks=4, start=MONDAY)


@pytest.mark.parametrize("goal", [
    {"details": None}, {"details": []}, {"details": "x"}, {"priority": None}, {"title": None}, {"title": ""}, {"target_date": "2026-11-20"}, {"target_date": None},
    {"details": {"distance_km": "x", "elevation_m": -4}}, {"details": {"distance_km": 1e9, "elevation_m": 1e9}}, {"details": {"distance_km": float("nan")}},
])
def test_malformed_goals_never_raise(goal):
    g = {**EVENT, **goal}
    g.pop("missing", None)
    p = build_profile(RUDY, [g], MONDAY)
    plan_weeks(p, MONDAY, weeks=2, start=MONDAY)
    advice(p)
    outlook(p, MONDAY)
    no_priority = {k: v for k, v in EVENT.items() if k != "priority"}
    build_profile(RUDY, [no_priority], MONDAY)


ABSURD = [None, 0, -1, -5.5, 1, 2.5, 7, 8, 99, 1e9, 1e308, float("inf"), float("nan"), 10**400, "abc", "", True, False, [], ["x"], {}, {"a": 1}, [[1]], [None], [{"a": 1}]]
NUMERIC_KEYS = ["constraints.training_days", "constraints.weekday_session_max_min", "constraints.weekend_session_max_min", "running.weeks_since_last_run", "running.weekly_km_8w",
                "running.weekly_km_12m", "running.best_10k_min", "running.hr_max", "running.longest_recent_min", "strength.sessions_per_week", "strength.sessions_per_week_12m",
                "body.birth_year", "trail.weekly_vert_m", "hybrid.crossfit_years"]
LIST_KEYS = ["sports.practiced", "multisport.blocked_days", "multisport.preferred_run_days", "goal.physique_focus", "hybrid.crossfit_skills", "history.injuries", "strength.level",
             "history.recent_break", "hybrid.hyrox_done", "hybrid.access"]


def test_absurd_or_missing_facts_never_raise_and_always_leave_a_message_or_a_plan():
    n = 0
    for key, value in product(NUMERIC_KEYS + LIST_KEYS, ABSURD):
        for sports in (["running", "strength", "hyrox"], ["crossfit"], ["strength"]):
            facts = {**BASE, "sports.practiced": sports, "constraints.training_days": 4, key: value}
            for goals in ([], [EVENT]):
                p = build_profile(facts, goals, MONDAY)
                sessions = plan_weeks(p, MONDAY, weeks=2, start=MONDAY)
                advice(p)
                outlook(p, MONDAY)
                n += 1
                assert sessions or empty_reason(p), (key, value)
                assert all(s.duration_min > 0 and math.isfinite(s.duration_min) for s in sessions), (key, value)
    assert n > 1000


def test_empty_facts_give_a_plan_or_a_clear_reason():
    p = build_profile({}, [], MONDAY)
    assert plan_weeks(p, MONDAY) == [] and "sports" in empty_reason(p)
    runner = build_profile({"sports.practiced": ["running"]}, [], MONDAY)
    assert plan_weeks(runner, MONDAY, weeks=2, start=MONDAY)


def test_profile_dataclass_defaults_are_safe():
    p = Profile()
    assert not p.no_days and p.notices == [] and p.injury_unknown == []


def test_every_new_message_has_a_full_english_translation():
    import re

    from app import i18n

    french = re.compile(r"[àâçéèêëîïôûùüÿœ]|\b(le|la|les|des|une|vos|votre|pour|dans|avec|est|séance|jours?|semaine)\b", re.I)
    scenarios = [
        ({**BASE, "sports.practiced": ["running", "strength", "hyrox"], "constraints.training_days": 4, "multisport.blocked_days": ["vendredi"]}, []),
        ({**BASE, "sports.practiced": ["running", "strength", "crossfit"], "constraints.training_days": 3, "multisport.blocked_days": ["samedi", "dimanche"]}, []),
        ({**BASE, "sports.practiced": ["crossfit"], "constraints.training_days": 6, "multisport.blocked_days": ["mardi", "jeudi", "samedi"]}, []),
        ({**BASE, "sports.practiced": ["running", "strength"], "multisport.blocked_days": DAYS[:5], "constraints.weekday_session_max_min": 30, "constraints.training_days": 5}, []),
        ({**BASE, "sports.practiced": ["running", "strength", "hyrox"], "constraints.weekday_session_max_min": 30, "constraints.weekend_session_max_min": 30}, []),
        ({**BASE, "sports.practiced": ["running", "strength"], "constraints.weekday_session_max_min": 45}, []),
        ({**BASE, "sports.practiced": ["running", "strength"], "constraints.training_days": 9, "constraints.weekday_session_max_min": 5, "constraints.weekend_session_max_min": 0,
          "running.best_10k_min": 5, "history.injuries": ["autre"], "history.injuries.other": "élongation du quadriceps"},
         [{**EVENT, "target_date": MONDAY - timedelta(days=3), "title": "Semi passé"}]),
        ({**BASE, "sports.practiced": ["running"], "constraints.training_days": 0, "constraints.weekday_session_max_min": -3, "constraints.weekend_session_max_min": 5}, []),
        ({**BASE, "sports.practiced": ["running"], "constraints.training_days": 1}, []),
        ({**BASE, "sports.practiced": ["running"], "constraints.training_days": 7}, []),
        ({**BASE, "sports.practiced": ["running"], "constraints.training_days": -2}, [{**EVENT, "title": "A"}, {**EVENT, "title": "B"}]),
        ({**BASE, "sports.practiced": ["running", "strength"], "multisport.blocked_days": DAYS[:6]}, []),
        ({**BASE, "sports.practiced": ["running"], "multisport.blocked_days": DAYS}, []),
        ({**BASE, "sports.practiced": []}, []),
    ]
    texts: set[str] = set()
    for facts, goals in scenarios:
        p = build_profile(facts, goals, MONDAY)
        texts |= set(warnings(p)) | {empty_reason(p)} | {n for s in plan_weeks(p, MONDAY, weeks=4, start=MONDAY) for n in s.notes}
    assert len(texts) > 20
    bad = sorted(t for t in texts if french.search(re.sub(r'(«|\").*?(»|\")', '', i18n.tr(t, "en"))))  # le texte saisi par la personne reste tel quel
    assert bad == []
