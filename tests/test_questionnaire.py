from pathlib import Path

from app.questionnaire.bank import load_bank, validate_bank
from app.questionnaire.conditions import evaluate, validate_condition
from app.questionnaire.engine import next_questions, pending, progress
from app.questionnaire.models import Fact

BANK_DIR = Path(__file__).parent.parent / "questions"


def F(key, value):
    return Fact(key=key, value=value)


def test_bank_is_valid():
    bank = load_bank(BANK_DIR)
    assert len(bank) > 20
    assert validate_bank(bank) == []


def test_conditions():
    facts = {"sports.practiced": ["running", "strength"], "n": 5}
    assert evaluate({"fact": "sports.practiced", "contains": "running"}, facts)
    assert not evaluate({"fact": "sports.practiced", "contains": "cycling"}, facts)
    assert evaluate({"fact": "n", "gte": 5}, facts)
    assert not evaluate({"fact": "absent", "eq": 1}, facts)
    assert evaluate({"fact": "absent", "exists": False}, facts)
    assert evaluate({"not": {"fact": "n", "lte": 2}}, facts)
    assert evaluate(None, facts)


def test_invalid_condition_rejected():
    for bad in ({"fact": "x"}, {"fact": "x", "eq": 1, "in": [1]}, {"all": []}, {"eq": 1}):
        try:
            validate_condition(bad)
        except ValueError:
            continue
        raise AssertionError(f"condition invalide acceptée : {bad}")


def test_flow_follows_answers():
    bank = load_bank(BANK_DIR)
    first = next_questions(bank, [], 1)[0]
    assert first.fact_key == "sports.practiced"

    ids = {q.id for q in pending(bank, [F("sports.practiced", ["strength"])])}
    assert "str.frequency" in ids
    assert "run.recent_volume" not in ids

    ids = {q.id for q in pending(bank, [F("sports.practiced", ["running", "trail"])])}
    assert "run.recent_volume" in ids
    assert "str.frequency" not in ids


def test_followup_appears_after_parent_answer():
    bank = load_bank(BANK_DIR)
    base = [F("sports.practiced", ["running"])]
    assert "run.longest_trail" not in {q.id for q in pending(bank, base)}
    base.append(F("running.trail_experience", "régulièrement"))
    assert "run.longest_trail" in {q.id for q in pending(bank, base)}


def test_latest_fact_wins_and_progress():
    bank = load_bank(BANK_DIR)
    facts = [F("sports.practiced", ["running"])]
    assert progress(bank, facts)["answered"] == 1
    assert "goal.sports" not in {q.id for q in pending(bank, facts)}


def test_validate_detects_problems():
    from app.questionnaire.models import Question

    q1 = Question(id="a", domain="goals", text="?", type="number", fact_key="k1",
                  show_if={"fact": "k2", "exists": True})
    q2 = Question(id="b", domain="goals", text="?", type="number", fact_key="k2",
                  show_if={"fact": "k1", "exists": True})
    q3 = Question(id="c", domain="goals", text="?", type="number", fact_key="k3",
                  show_if={"fact": "inconnu", "eq": 1})
    problems = validate_bank([q1, q2, q3])
    assert any("cycle" in p for p in problems)
    assert any("personne ne produit" in p for p in problems)


def test_multisport_questions_need_two_sports():
    bank = load_bank(BANK_DIR)
    one = {q.id for q in pending(bank, [F("sports.practiced", ["running"])])}
    assert "ms.priority" not in one
    two = {q.id for q in pending(bank, [F("sports.practiced", ["running", "strength"])])}
    assert {"ms.priority", "ms.leg_fatigue", "ms.run_days", "ms.strength_days"} <= two


def test_red_flag_followup_and_health_first():
    bank = load_bank(BANK_DIR)
    base = [F("sports.practiced", ["running"])]
    assert "he.medical_advice" not in {q.id for q in pending(bank, base)}
    flagged = [*base, F("health.red_flags", ["palpitations"])]
    assert "he.medical_advice" in {q.id for q in pending(bank, flagged)}
    clear = [*base, F("health.red_flags", ["aucun"])]
    assert "he.medical_advice" not in {q.id for q in pending(bank, clear)}


def test_hyrox_crossfit_branches():
    bank = load_bank(BANK_DIR)
    ids = {q.id for q in pending(bank, [F("sports.practiced", ["hyrox"])])}
    assert "hy.hyrox_weak" in ids and "hy.cf_years" not in ids
    done = [F("sports.practiced", ["hyrox"]), F("hybrid.hyrox_done", "jamais")]
    ids = {q.id for q in pending(bank, done)}
    assert "hy.hyrox_time" not in ids


def test_trail_deepening_branches():
    bank = load_bank(BANK_DIR)
    ids = {q.id for q in pending(bank, [F("sports.practiced", ["running"])])}
    assert not any(i.startswith("tr.") for i in ids)
    ids = {q.id for q in pending(bank, [F("sports.practiced", ["trail"])])}
    assert "tr.distance" in ids and "tr.elevation" not in ids
    facts = [F("sports.practiced", ["trail"]), F("trail.target_distance", "80 à 120 km")]
    ids = {q.id for q in pending(bank, facts)}
    assert {"tr.elevation", "tr.poles", "tr.night"} <= ids
    facts = [F("sports.practiced", ["trail"]), F("trail.target_distance", "pas encore défini")]
    ids = {q.id for q in pending(bank, facts)}
    assert "tr.elevation" not in ids


def test_skipped_question_is_not_asked_again_and_counts_as_absent():
    bank = load_bank(BANK_DIR)
    facts = [F("sports.practiced", ["hyrox"]), F("hybrid.hyrox_done", None)]
    ids = {q.id for q in pending(bank, facts)}
    assert "hy.hyrox_done" not in ids
    assert "hy.hyrox_time" not in ids  # condition sur un fait passé : absente


def test_multi_goal_conditions_and_history_depth():
    bank = load_bank(BANK_DIR)
    goals = ["perte de gras", "performance"]
    facts = [F("sports.practiced", ["running"]), F("goal.primary", goals), F("history.sport_years", 6), F("running.weekly_km_8w", 30)]
    ids = {q.id for q in pending(bank, facts)}
    assert "goal.physique" in ids  # `in` sur une réponse multiple
    entries = [q for q in bank if q.type == "entries"]
    assert len(entries) >= 6 and all(q.fields for q in entries)
    assert {"his.sports_past", "his.peaks", "his.injury_timeline", "run.history_years"} <= ids
    assert "str.history_years" not in ids
    p = progress(bank, facts)
    assert "history" in p["domains"] and p["domains"]["history"]["remaining"] > 5


def test_project_is_last_and_dates_are_validated():
    from app.questionnaire.answers import AnswerError, to_facts

    bank = load_bank(BANK_DIR)
    todo = pending(bank, [F("sports.practiced", ["running"])])
    assert todo[-1].domain == "project"
    goals = next(q for q in bank if q.id == "pj.upcoming")
    ok = to_facts(goals, [{"what": "Déménagement", "when": "2027-06-12", "impact": "moins de temps"}])
    assert ok[0].value[0]["when"] == "2027-06-12"
    try:
        to_facts(goals, [{"what": "x", "when": "bientôt", "impact": "moins de temps"}])
    except AnswerError:
        return
    raise AssertionError("date invalide acceptée")


def test_beginner_is_not_asked_about_records_or_past_performance():
    bank = load_bank(BANK_DIR)
    novice = [F("sports.practiced", ["running", "strength", "trail"]), F("history.sport_years", 0), F("running.weekly_km_8w", 0), F("strength.level", "débutant")]
    ids = {q.id for q in pending(bank, novice)}
    hidden = {"his.peaks", "his.competitions", "his.sports_past", "his.start_age", "his.injury_timeline", "run.best_10k", "run.longest", "run.hr_max",
              "run.trail_experience", "run.history_years", "tr.downhill", "tr.vert_week", "str.lifts", "str.pullups", "str.split", "str.history_years"}
    assert not hidden & ids, hidden & ids
    assert {"his.injuries", "his.activity_now", "con.days", "str.frequency"} <= ids  # sécurité, disponibilités et objectifs restent demandés
    expert = [*novice[:1], F("history.sport_years", 8), F("running.weekly_km_8w", 40), F("strength.level", "avancé"), F("running.trail_experience", "régulièrement")]
    ids2 = {q.id for q in pending(bank, expert)}
    assert {"his.peaks", "run.best_10k", "run.hr_max", "str.lifts", "str.pullups", "tr.downhill"} <= ids2
