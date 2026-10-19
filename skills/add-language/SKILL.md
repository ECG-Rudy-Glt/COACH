---
name: add-language
description: Translate COACH (UI strings, questionnaire, engine texts, LLM prompts) into another language without breaking identifiers, rules or tests. Use for an English UI or any new locale.
---

# Add a language

State today: the code and docs are English; **user-facing text is French** and lives in four places.

| Layer | Where | Notes |
|---|---|---|
| UI | `app/static/app.js`, `index.html` | strings are inline literals; step 1 is extracting them into a `t("key")` table (`app/static/i18n/<lang>.json`) loaded before `app.js` |
| Questionnaire | `questions/*.yaml` (`label`, `help`, option labels) | keep `id`, option **values** and `show_if` untouched; translate labels only |
| Engine texts | `app/plan/*.py`, `app/nutrition/engine.py`, `app/exercises/labels.py` | session titles, notes, advice, muscle/equipment labels |
| LLM prompts | `app/coach/*.py`, `app/nutrition/analyze.py` | translate system prompts and the answer language instruction |
| Evidence | `data/evidence/*.yaml` (`finding_fr`, `limits_fr`) | add `finding_en`/`limits_en`; fall back to the other language when missing |

## Steps
1. Introduce a locale setting (`LOCALE` env + per-user preference) and a tiny `t()` helper on server and client. Do not scatter `if lang ==` in logic.
2. Extract strings **mechanically first** (no wording changes) and make the French output byte-identical — the existing tests are your safety net.
3. Add the new locale file; translate with care for tone (formal/informal address differs by language) and units (kg/lb, km/mi — conversion must happen at display, storage stays metric).
4. Translate prompts together with the “answer language” instruction; keep JSON keys, rule IDs and action names in English.
5. Tests: a locale smoke test that renders every question and every session kind without missing keys; keep the French suite green.

## Pitfalls
- Don’t translate identifiers, enum values or CSS class names.
- Pluralisation and date formats: use `Intl` on the client.
- Health wording is safety-relevant: have a native speaker review the disclaimers and red-flag messages.
