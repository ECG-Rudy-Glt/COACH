"""Replanification de la fin de semaine (G13 à G17) : un test par règle, cas de l'exemple (course manquée mercredi), parité des sources."""
from datetime import date, timedelta

import yaml

from app.coach import service
from app.plan.engine import build_profile, plan_weeks
from app.plan.replan import KEY, SOURCES, replan_rest_of_week
from tests.test_plan import RUDY

MON = date(2026, 10, 5)
WED = date(2026, 10, 7)


def week_rows(facts=None, done=(), skipped=()):
    """Semaine du plan en lignes de base de données ; `done` : (jour, type) déjà faits."""
    p = build_profile({**RUDY, **(facts or {})}, [], MON)
    rows = []
    for i, s in enumerate(plan_weeks(p, MON, 1, start=MON), 1):
        status = "done" if (s.date, s.kind) in done else "skipped" if (s.date, s.kind) in skipped else "planned"
        rows.append({"id": i, "day": s.date, "kind": s.kind, "title": s.title, "duration_min": s.duration_min, "details": dict(s.details), "rules": s.rules,
                     "notes": s.notes, "status": status, "logged": {"minutes": s.duration_min} if status == "done" else None})
    return p, rows


def run(facts=None, done=(), today=WED, **kw):
    p, rows = week_rows(facts, done)
    return p, rows, replan_rest_of_week(p, rows, [], today, **kw)


EXAMPLE_DONE = {(MON, "run_easy"), (MON, "strength_upper"), (date(2026, 10, 6), "strength_lower")}


def test_example_missed_run_moves_to_tomorrow_with_pairing():
    """Course et haut du corps manqués mercredi : jeudi (demain), la sortie longue du samedi reste ; aucune séance en plus."""
    _, rows, out = run(done=EXAMPLE_DONE)
    ch = {c["session_id"]: c for c in out["changes"]}
    assert len(ch) == 3 and all(c["missed"] for c in ch.values() if c["from"] == WED.isoformat())
    run_c = next(c for c in ch.values() if c["kind"] == "run_easy")
    assert run_c["to"] == "2026-10-08" and run_c["duration_to"] == run_c["duration_from"]
    assert next(c for c in ch.values() if c["kind"] == "run_long")["action"] == "keep"
    assert sum(len(d["sessions"]) for d in out["days"]) == 3


def test_g13_never_creates_or_doubles_a_session():
    _, rows, out = run(done=EXAMPLE_DONE)
    placed = [s["session_id"] for d in out["days"] for s in d["sessions"]]
    assert len(placed) == len(set(placed)) <= len([r for r in rows if r["status"] == "planned"])
    assert {r["id"] for r in rows if r["status"] == "planned"} >= set(placed)
    assert "G13" in {a["rule"] for a in out["applied"]}


def test_g13_nothing_to_replan():
    p, rows = week_rows()
    assert replan_rest_of_week(p, rows, [], date(2026, 10, 11))["empty"]  # dimanche : plus de jour restant
    assert replan_rest_of_week(p, [r for r in rows if False], [], WED)["empty"]


def test_g14_volume_never_exceeds_plan_and_is_restored_when_low():
    p, rows = week_rows()
    target = sum(r["duration_min"] for r in rows if r["kind"].startswith("run_"))
    for r in rows:
        if (r["day"], r["kind"]) in EXAMPLE_DONE:
            r["status"], r["logged"] = "done", {"minutes": r["duration_min"]}
    out = replan_rest_of_week(p, rows, [], WED)
    v = out["volume"]
    assert v["done_min"] + v["planned_min"] <= target
    # séance faite plus courte que prévu : les footings à venir sont allongés de 20 % au plus, sans dépasser le prévu
    for r in rows:
        if r["status"] == "done" and r["kind"] == "run_easy":
            r["logged"] = {"minutes": 20}
    out = replan_rest_of_week(p, rows, [], WED)
    c = next(c for c in out["changes"] if c["kind"] == "run_easy")
    assert c["duration_to"] <= round(c["duration_from"] * 1.2) + 5 and out["volume"]["done_min"] + out["volume"]["planned_min"] <= target


def test_g14_no_stretch_with_run_injury_and_cut_when_done_exceeds_plan():
    p, rows = week_rows()
    for r in rows:
        if (r["day"], r["kind"]) in EXAMPLE_DONE:
            r["status"], r["logged"] = "done", {"minutes": r["duration_min"]}
            if r["kind"] == "run_easy":
                r["logged"] = {"minutes": 20}
    p.run_injury = True
    out = replan_rest_of_week(p, rows, [], WED)
    assert next(c for c in out["changes"] if c["kind"] == "run_easy")["duration_to"] == 60  # S2 : jamais allongé
    p.run_injury = False
    acts = [{"day": MON, "minutes": 90, "run": True}]  # activité de course non reliée : elle compte dans le volume fait
    out = replan_rest_of_week(p, rows, acts, WED)
    assert out["volume"]["done_min"] == 110
    assert next(c for c in out["changes"] if c["kind"] == "run_easy")["duration_to"] == 20  # le footing cède d'abord, jamais sous 20 min ; la sortie longue n'est pas touchée
    assert any(a["rule"] == "G14" for a in out["applied"])


def test_g15_no_back_to_back_hard_sessions():
    """Sortie longue manquée vendredi-samedi : elle ne se colle pas à la séance de jambes déjà faite."""
    p, rows = week_rows(done={(MON, "run_easy"), (MON, "strength_upper"), (date(2026, 10, 6), "strength_lower"), (WED, "run_easy"), (WED, "strength_upper")})
    for r in rows:
        if r["status"] == "planned":
            r["day"] = date(2026, 10, 6) if r["kind"] == "run_long" else r["day"]
    out = replan_rest_of_week(p, rows, [], WED)
    c = next(c for c in out["changes"] if c["kind"] == "run_long")
    assert c["to"] != "2026-10-06" and (c["to"] is None or abs((date.fromisoformat(c["to"]) - date(2026, 10, 6)).days) >= 2)
    hard_days = [date.fromisoformat(c["to"]) for c in out["changes"] if c["to"] and c["kind"] in KEY] + [date(2026, 10, 6)]
    assert all(abs((a - b).days) >= 2 for i, a in enumerate(hard_days) for b in hard_days[i + 1:])


def test_g15_respects_blocked_days_caps_and_bad_weather():
    p, rows = week_rows(done=EXAMPLE_DONE)
    out = replan_rest_of_week(p, rows, [], WED, avoid_days={date(2026, 10, 8)})
    run_c = next(c for c in out["changes"] if c["kind"] == "run_easy")
    assert run_c["to"] not in ("2026-10-08", "2026-10-09")  # jeudi : météo ; vendredi : jour bloqué (G6)
    assert any(a["rule"] == "W7" for a in out["applied"])
    assert all(date.fromisoformat(d["day"]).weekday() != 4 or not d["sessions"] for d in out["days"])


def test_g16_keeps_a_rest_day():
    p, rows = week_rows(facts={"constraints.training_days": 6, "multisport.blocked_days": []}, done={(MON, "run_easy"), (MON, "strength_upper")})
    out = replan_rest_of_week(p, rows, [], MON)
    days = {date.fromisoformat(d["day"]) for d in out["days"] if d["sessions"]} | {r["day"] for r in rows if r["status"] == "done"}
    assert len(days) <= 6


def test_g17_too_few_days_drops_and_says_so():
    """Jeudi seul disponible (le reste bloqué) : on garde le plus prioritaire et on retire le reste en le disant."""
    p, rows = week_rows(facts={"multisport.blocked_days": ["vendredi", "samedi", "dimanche"]}, done=EXAMPLE_DONE)
    out = replan_rest_of_week(p, rows, [], WED)
    kept = [c for c in out["changes"] if c["to"]]
    assert len(kept) <= 2 and any(c["action"] == "drop" for c in out["changes"])
    assert any(a["rule"] == "G17" for a in out["applied"]) and out["notes"]
    assert replan_rest_of_week(p, rows, [], WED)["changes"] == out["changes"]  # déterministe


def test_sources_are_real_and_rules_documented():
    ids = {e["id"] for f in (service.ROOT / "data" / "evidence").glob("*.yaml") for e in yaml.safe_load(f.read_text(encoding="utf-8"))}
    digest = yaml.safe_load((service.ROOT / "data" / "rules_digest.yaml").read_text(encoding="utf-8"))
    doc = (service.ROOT / "docs" / "rules.md").read_text(encoding="utf-8")
    for rule, src in SOURCES.items():
        assert rule in digest and f"| {rule} |" in doc
        assert set(src["ids"]) <= ids
        assert src["ids"] or src["convention"]
    assert MON + timedelta(days=2) == WED
