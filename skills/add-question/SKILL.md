---
name: add-question
description: Add or modify questions in the adaptive questionnaire (questions/*.yaml) that feed the profile facts. Use when the engine needs a new input.
---

# Add a question

## Steps
1. Choose the domain file in `questions/` (running, strength, health, goals, constraints…) and read neighbouring entries for format: `id` (`domain.name`), `label`, `type`, `options`/bounds, `required`/priority, optional `show_if` conditions, and the fact key it writes.
2. A question must change a decision. If no engine code reads the fact, don’t ask it (the questionnaire is adaptive for a reason).
3. Use closed options and numeric bounds wherever possible; add an “other (free text)” escape only when needed. Free text is untrusted data.
4. Conditions: `show_if` can only reference earlier facts; avoid cycles. `validate_bank` runs at start-up and in tests and rejects dangling references.
5. If the fact feeds the plan/nutrition engine, read it in `build_profile()` with a safe default when missing, and add a test.
6. Sensitive questions (health, injuries, medication, body image): explain *why* it is asked in the helper text, allow “prefer not to say”, never send the raw answer to an LLM unless the prompt needs it.

## Verify
`pytest tests/test_questionnaire.py tests/test_answers.py -q`; walk the flow in the UI for a beginner and an advanced profile.
