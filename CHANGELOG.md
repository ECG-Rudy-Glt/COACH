# Changelog

All notable changes are documented here. Format: [Keep a Changelog](https://keepachangelog.com/en/1.1.0/), versioning: [SemVer](https://semver.org/) (pre-1.0: minor versions may break).

## [Unreleased]
### Added
- Plan screen: *Table* view of the week, one column per day like a kanban board; long-press a card then drag it to another day (touch on iPhone and Android, mouse on desktop; the board scrolls by itself near the edges). The choice of view is remembered.
- Interactive onboarding: welcome screen, 13 essential questions, a loading page while the coach AI reads the profile, then either the app or *Your coach asks* (missing questions chosen by the model among the bank, validated and bounded by the server, with a rule-based fallback and free-text clarifications). First plan generated at the end. See `docs/onboarding.md`.
- Profile page: the answered questions are grouped in collapsible sections.
- Garmin matching: activities are linked to sessions logged by hand as well as planned ones (same day, same sport, closest duration), every time the plan opens and after each sync; the old matcher was only used by tests. Off-plan activities can be linked manually to a session (the session then moves to the day it was really done), and unlinked again.
- Reschedule a session: *Change day* on the session screen (bottom sheet, any date in range) or long-press then drag the session onto a day (touch on iPhone and Android, mouse on desktop). Non-blocking warnings for two hard sessions within 48 h or legs next to a key run (G5, I1, I2); the original day is kept (`moved_from`).
- Long-horizon trajectory for dated *performance* goals (e.g. 10 km under 40 min in two years): current level from race records (C10), base → threshold → specific → taper phases with timed checkpoints every 3 months (C11), and a weekly-volume target instead of an unbounded build (C12). Exposed as `trajectory` on `GET /users/{id}/plan`, shown in the plan screen and given to the coach.
- Threshold and goal-pace quality sessions during those phases; an undated or conflicting ultra is reported instead of silently ignored.
- Meal form: *Lunchbox for tomorrow* — a meal prepared (and estimated) the evening before is saved on tomorrow's lunch, so its calories count on the day it is eaten; the day arrows now reach tomorrow.
- Meal form: portion size (small / normal / big plate) is passed to the estimator.
### Changed
- Meal estimates: the prompt now asks for the high end of the range for big plates (sauces, cooking fat, restaurant portions) and the per-meal ceiling is raised from 2,500 to 3,500 kcal; estimates were clipped and too low.
- Meal photo: two large buttons (*Take a photo* opens the camera directly on iPhone and Android, *Photo library*), preview with a remove button, and tips for a better estimate. `[hidden]` now always hides an element (the chat suggestion chips did not disappear while typing).
- LLM providers: per-provider JSON mode (`json_mode` in `data/llm_providers.yaml`, `LLM_JSON_MODE` override) for the weekly review, notifications and meal estimates, and a graceful fallback without tool calling (`LLM_TOOLS`, catalog `tools` flag, or a server that refuses the option). Adapter tests use sample provider responses (`tests/fixtures/llm`).
- `app/repo.py` (880 lines) split into the `app/repo/` package, one module per domain behind the same `Repo` protocol; `from app.repo import MemoryRepo, PostgresRepo, Repo` keeps working. No SQL or behaviour change (method sources are identical, PostgreSQL tests pass).
- Plan screen: the cycle, objective, trajectory and coach-review cards at the top are collapsible (title and one-line summary stay visible, the state is remembered per card; the coach review opens by itself when a proposal or a question is waiting).
- Coach chat: typing indicator, animated bubbles, composer pinned above the tab bar with an auto-growing field and a round send button (Enter sends on desktop), suggestion chips, and an inline *Retry* instead of a lost message.
- Release process documented in `docs/releasing.md`; a CI check requires a `CHANGELOG.md` entry when code, migrations, questions or rule data change.
- CI reports test coverage (job summary) and fails below a minimum threshold (`.coveragerc`, currently 83 %).
- Background jobs start from a FastAPI lifespan handler instead of the deprecated `on_event` hook (no behaviour change).
### Fixed
- The plan no longer schedules sessions on the day of the event (whatever the weekday), keeps the day before short and easy, and leaves 2 days without running after it (rule C6).
- A declared pain on a zone that carries running (knee, ankle, hip, shin, Achilles, calf, foot, hamstring) now freezes running volume, long run and intensity (rule S2); calf, foot and hamstring pain are recognised in session notes.
- Individual exercises can be excluded with the `history.avoid_exercises` fact (name fragments) without treating the whole body zone as injured.
- With no event within reach, the weekly volume no longer keeps growing until the schedule cap.

## [0.1.0] — 2026-10-19 — first public release
### Added
- Rules-based multisport plan engine with cycles/phases, nutrition engine, adaptive questionnaire (97 questions).
- 60 publications (abstract-level summaries, DOI/PMID checked) linked to rule IDs; a full human review is tracked on the issue board; exercise library import (wger + free-exercise-db).
- LLM coach (weekly review, chat with read-only history tools, notifications) behind a **multi-provider layer**: Anthropic, OpenAI, Gemini, Mistral, OpenRouter, Ollama, any OpenAI-compatible server, or none.
- Garmin Connect sync with automatic session matching.
- Docker Compose stack: internal database network, file secrets (`NAME_FILE`), optional HTTPS proxy, backups and local LLM profiles; one-shot exercise import.
- PWA (iPhone/Android), web push / ntfy / e-mail notifications.
### Security
- Dependencies updated to fix known Starlette advisories (FastAPI 0.147, Starlette ≥ 1.3.1); Dependabot now runs monthly and grouped.
- CSP and security headers, same-origin write check, per-account and per-IP login throttling, registration closes after the first account by default, API docs disabled by default, hardened containers.
