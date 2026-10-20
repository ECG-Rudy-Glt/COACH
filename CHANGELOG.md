# Changelog

All notable changes are documented here. Format: [Keep a Changelog](https://keepachangelog.com/en/1.1.0/), versioning: [SemVer](https://semver.org/) (pre-1.0: minor versions may break).

## [Unreleased]
### Added
- Long-horizon trajectory for dated *performance* goals (e.g. 10 km under 40 min in two years): current level from race records (C10), base → threshold → specific → taper phases with timed checkpoints every 3 months (C11), and a weekly-volume target instead of an unbounded build (C12). Exposed as `trajectory` on `GET /users/{id}/plan`, shown in the plan screen and given to the coach.
- Threshold and goal-pace quality sessions during those phases; an undated or conflicting ultra is reported instead of silently ignored.
### Changed
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
