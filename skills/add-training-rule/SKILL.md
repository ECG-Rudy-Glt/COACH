---
name: add-training-rule
description: Add or modify a deterministic training or nutrition rule in COACH with its ID, evidence level and test. Use for changes to plan generation, zones, volumes, recovery, nutrition targets.
---

# Add or change a rule

Rules are the product. A rule without ID, evidence level and test must not be merged.

## Steps
1. Write the rule in `docs/rules.md` under the right section: **ID** (next free in its family: C, M, G, I, N…), the value/threshold, the **evidence level** (A solid, B moderate, C field practice — be honest) and the observable **effect**.
2. Mirror it in `data/rules_digest.yaml` (short text the LLM may cite). The digest test fails if `rules.md` and the digest diverge.
3. Implement in the engine (`app/plan/*.py` or `app/nutrition/engine.py`). Keep functions pure: facts in, sessions/targets out. Attach the rule ID to the session’s `rules` list so the UI and coach can cite it.
4. Tests (`tests/test_plan.py`, `tests/test_nutrition.py`): the nominal case, **boundaries** (week 1 vs deload, injury, no available days, just-finished event), and a case proving the rule *does not* fire when it should not.
5. If a publication supports it, add it via `add-evidence` and list the rule in its `applies_to`.
6. `CHANGELOG.md` entry; note any behaviour change for existing users’ upcoming weeks.

## Pitfalls
- Prudence by default: when data is missing, reduce, never extrapolate.
- Conflicting rules (same ID reused, two rules fighting for a day) are bugs — search for the ID across `app/` and `docs/` first.
- Don’t encode medical thresholds as advice; route red flags to “see a professional” text.
- Same input must give the same plan (no randomness, no `date.today()` deep inside engines: pass `today`).

## Verify
`pytest tests/test_plan.py tests/test_nutrition.py tests/test_coach.py -q`, then generate a plan for 3 contrasting profiles and read the sessions.
