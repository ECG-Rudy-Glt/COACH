"""Le moteur s'adapte au niveau : débutant, amateur, confirmé, haut niveau. Les invariants de sécurité tiennent pour tous (G1, G5, I1, I2, G6)."""
from datetime import date, timedelta

import pytest

from app.plan.engine import build_profile, plan_weeks

TODAY = date(2026, 11, 2)  # un lundi


def event(title, km, weeks):
    return [{"status": "active", "kind": "event", "title": title, "target_date": TODAY + timedelta(weeks=weeks), "priority": "principal", "details": {"distance_km": km}}]


PERSONAS = {
    "debutant": ({"sports.practiced": ["running"], "constraints.training_days": 3, "running.weekly_km_8w": 0, "strength.level": "débutant"}, []),
    "debutant_10k": ({"sports.practiced": ["running", "strength"], "constraints.training_days": 3, "running.weekly_km_8w": 6, "running.best_10k_min": 70}, event("10 km", 10, 12)),
    "amateur": ({"sports.practiced": ["running", "strength"], "constraints.training_days": 4, "running.weekly_km_8w": 30, "running.best_10k_min": 50, "strength.level": "intermédiaire"},
                event("Semi", 21.1, 10)),
    "confirme": ({"sports.practiced": ["running", "strength"], "constraints.training_days": 5, "running.weekly_km_8w": 60, "running.best_10k_min": 40, "strength.level": "intermédiaire"},
                 event("Marathon", 42.2, 14)),
    "elite": ({"sports.practiced": ["running", "strength"], "constraints.training_days": 7, "constraints.weekday_session_max_min": 150, "constraints.weekend_session_max_min": 200,
               "running.weekly_km_8w": 140, "running.best_10k_min": 30.5, "strength.level": "avancé"}, event("Marathon", 42.2, 14)),
}


def weeks(name):
    facts, goals = PERSONAS[name]
    p = build_profile(facts, goals, TODAY)
    out = {}
    for s in plan_weeks(p, TODAY, 8):
        out.setdefault(s.date - timedelta(days=s.date.weekday()), []).append(s)
    return p, [out[k] for k in sorted(out)]


def run_min(week):
    return sum(s.duration_min for s in week if s.kind.startswith("run_"))


@pytest.mark.parametrize("name", PERSONAS)
def test_every_level_keeps_the_safety_invariants(name):
    p, wk = weeks(name)
    assert len(wk) == 8
    for w in wk:
        days = {s.date for s in w}
        assert len(days) <= 6  # G5 : un jour de repos
        hard = sorted(s.date for s in w if s.kind in ("run_long", "run_quality"))
        assert all((b - a).days >= 2 for a, b in zip(hard, hard[1:], strict=False))  # G5 : 48 h entre séances clés
        lower = [s.date for s in w if s.kind == "strength_lower"]
        assert all(abs((h - d).days) >= 2 for h in hard for d in lower)  # I1, I2
    vols = [run_min(w) for w in wk]
    peak = vols[0]
    for v in vols[1:]:  # une semaine allégée remonte vers le pic précédent, jamais au-delà de G1 
        assert v <= peak * 1.2  # C9 : la sortie guidée par l'objectif dépasse volontairement G1
        peak = max(peak, v)


def test_volume_scales_with_level():
    totals = {n: max(run_min(w) for w in weeks(n)[1]) for n in PERSONAS}
    assert totals["debutant"] < totals["amateur"] < totals["confirme"] < totals["elite"]
    assert totals["debutant"] <= 150  # un débutant ne court pas plus de ~2 h 30 par semaine
    assert totals["elite"] >= 450  # un sportif de haut niveau n'est pas bridé à un volume d'amateur


def test_beginners_get_no_intensity_before_a_base_and_advanced_get_quality():
    assert not any(s.kind == "run_quality" for w in weeks("debutant")[1] for s in w)
    assert not any(s.kind == "run_quality" for s in weeks("debutant_10k")[1][0])
    assert any(s.kind == "run_quality" for w in weeks("elite")[1] for s in w)


@pytest.mark.parametrize("level,per_week", [("débutant", 3), ("intermédiaire", 4), ("avancé", 3)])
def test_strength_only_without_declared_duration_is_not_silently_cut(level, per_week):
    facts = {"sports.practiced": ["strength"], "constraints.training_days": per_week, "strength.sessions_per_week": per_week, "strength.level": level}
    kinds = [s.kind for s in plan_weeks(build_profile(facts, [], TODAY), TODAY, 1)]
    assert len(kinds) >= min(per_week, 3)  # le défaut de 60 min ne supprime plus les séances de force
