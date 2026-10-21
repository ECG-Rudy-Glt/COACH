# AGENTS.md — guide for AI coding assistants (and humans in a hurry)

You are working on **COACH**, a self-hosted sports coach. Read [README.md](README.md) and [docs/architecture.md](docs/architecture.md) first (5 minutes). Then pick the matching recipe in [`skills/`](skills/).

## Non-negotiable rules

1. **Numbers come from the rule engine, never from an LLM.** Plans, volumes, intensities and nutrition targets are deterministic. An LLM may explain and *propose bounded adjustments* that the server validates.
2. **Every training/nutrition rule has an ID, an evidence level and a test.** No rule without a row in `docs/rules.md` + `data/rules_digest.yaml`.
3. **Never invent a citation.** Publications in `data/evidence/` must have been opened and read (DOI/PMID/URL). Unsure → leave it out.
4. **Per-user isolation on every route.** Routes under `/users/{user_id}/…` must depend on `require_user`.
5. **No secrets in code, logs, prompts, tests or fixtures.** Secrets come from `NAME_FILE`/env via `app.config.env()`.
6. **No identity data to an LLM** (name, e-mail). Tests check this.
7. **Everything external is optional.** The app must start and plan with no LLM key, no wearable, no notification channel.
8. **Health-safety wording**: never present output as medical advice; red-flag symptoms → recommend a professional.

## Commands

```sh
python3 -m venv .venv && .venv/bin/pip install -r requirements-dev.txt
.venv/bin/ruff check . --fix && .venv/bin/pytest -q       # must both pass before you finish
.venv/bin/pytest -q --cov                              # coverage; CI fails below the threshold in .coveragerc
docker compose config -q                                    # validates compose changes
docker compose up -d --build                                # full stack (see README)
TEST_DATABASE_URL=postgresql://… .venv/bin/pytest tests/test_postgres.py   # DB-backed tests
```

No database is needed for the normal test suite: `MemoryRepo` mirrors `PostgresRepo`.

## Layout cheat-sheet

```
app/main.py            assembly, middleware, routers          app/repo/         Repo protocol + MemoryRepo + PostgresRepo, split by domain
app/auth.py            accounts, sessions, throttling         app/config.py     env()/NAME_FILE, DB URL
app/plan/              plan engine (deterministic)            app/nutrition/    nutrition engine + meal analysis
app/questionnaire/     question bank engine                   app/exercises/    library API + importer
app/coach/             llm.py providers · service.py review · chat.py · notify.py · history.py tools
app/garmin/            adapter, sync, matching, token crypto  app/static/       vanilla-JS PWA (no build step)
questions/*.yaml       question bank                          data/             rules digest, evidence, LLM catalog
db/migrations/         forward-only SQL                       docs/             human documentation
```

## Conventions

- Python 3.12, type hints, `ruff` (line length 200), no new heavy dependencies without discussion (see `THIRD_PARTY.md`).
- Any new persistence = migration + `Repo` protocol method + **both** implementations (the domain's `…Memory` and `…Postgres` classes in `app/repo/<domain>.py`) + test.
- Parse separately from I/O (`parse_*` pure functions) so tests need no network.
- User-visible strings are written in French (the source language) and translated through `app/static/i18n/<lang>.json` (French text = key, see [docs/i18n.md](docs/i18n.md)). Add the English translation of any new text (`python scripts/i18n_check.py`, `tests/test_i18n.py`), keep texts in the UI/engine and not scattered in logic, and don't mix languages inside one sentence.
- Frontend: plain JS in `app/static/app.js`, no framework or bundler; strict CSP means **no inline `<script>` and no `eval`**. Bump the cache name in `sw.js` when shell files change.
- Comments explain *why* (constraints, sources), not what.
- Commits: conventional style (`feat(plan): …`, `fix(auth): …`, `docs: …`). One concern per PR.

## Definition of done

- [ ] `ruff` and `pytest` pass; new behaviour has tests, including a failure case.
- [ ] Docs updated (`docs/` and, if a rule/env var/endpoint changed, the relevant table).
- [ ] `CHANGELOG.md` entry under *Unreleased*.
- [ ] No secret, personal path, IP or domain in the diff.
- [ ] Security checklist from `skills/security-review` applied when touching auth, routes, uploads, outbound requests or prompts.

## Where NOT to go

- Do not add telemetry, analytics or third-party scripts.
- Do not let an LLM write to the database, change a number owned by the engine, or choose a medication/supplement dose.
- Do not weaken `check_proposal`, the CSP, the same-origin check or the per-user guard to make a feature easier.
- Do not commit `secrets/`, `.env`, dumps or real user data (use synthetic fixtures).

## Working in this repository via pull requests

`main` is protected: work on a branch (or a fork), open a PR, wait for CI. See [CONTRIBUTING.md](CONTRIBUTING.md).
