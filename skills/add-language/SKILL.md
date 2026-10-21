---
name: add-language
description: Translate COACH (UI strings, questionnaire, engine texts, notifications, LLM prompts) into another language without breaking identifiers, rules or tests. Use to add a locale or to translate a new text.
---

# Add a language

French is the source language and English is shipped. Read [docs/i18n.md](../../docs/i18n.md) first: the **French text is the key** of one dictionary shared by the browser and the server.

| Layer | Where | Notes |
|---|---|---|
| UI, engine texts, errors | `app/static/i18n/<lang>.json` | exact text or template with holes (`{name}`, `{v}` optional suffix, `{num}` number); applied by `app/static/i18n.js` and `app/i18n.py` |
| Questionnaire | `questions/i18n/<lang>/*.yaml` | `text`, `help`, `unit`, `options` (stored value → label), `fields`; keep ids, values and `show_if` untouched |
| Notifications, e-mails | `i18n.tr()` in `app/coach/notify.py` | uses the same dictionary, in the user's language |
| LLM prompts | `data/prompts/<lang>.yaml` | one prompt per feature, with an explicit `LANGUAGE:` line; JSON keys, rule ids and action names stay in French/English as in the code |
| Evidence | `data/evidence/*.yaml` (`finding_fr`, `limits_fr`) | not translated yet: add `finding_en`/`limits_en` and fall back to French |

## Steps
1. Register the code in `app/i18n.py` (`SUPPORTED`, `LANG_NAMES`) and `app/static/i18n.js` (`LOCALES`); add the dictionary to `SHELL` in `sw.js` and bump the cache name.
2. Copy `en.json` and translate the values (keep every `{hole}`); `python scripts/i18n_check.py <lang>` lists what is missing.
3. Translate the questionnaire files and the prompts; mind tone (formal/informal address) and units (storage stays metric).
4. `pytest tests/test_i18n.py` must pass: it renders every question, session kind and notification without a missing translation.

## Adding a text in the code
Write it in French, then add its translation to `en.json` (same holes). Prefer `__("Dans {days} jours", { days })` in `app.js` over string concatenation so that word order can change.

## Pitfalls
- Don't translate identifiers, enum values or CSS class names. Option values are stored in French; only labels change.
- A template hole captures anything: keep the fixed part distinctive, use `{num}` for numbers.
- Pluralisation and dates: `Intl` on the client (`I18N.tag()`), `{v}` for a trailing "s".
- Health wording is safety-relevant: have a native speaker review the disclaimers and red-flag messages.
