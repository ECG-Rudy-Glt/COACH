# Contributing to COACH

Thanks for helping! Because COACH handles health data and gives training advice, we value **correctness, safety and small reviewable changes** over speed.

## The workflow (everyone, including maintainers)

`main` is protected: nobody pushes to it directly.

1. **Open or find an issue** first for anything non-trivial — it avoids duplicate work. Good first issues are labelled `good first issue`; the [project board](https://github.com/ECG-Rudy-Glt/COACH/projects) tracks status (Backlog → Ready → In progress → In review → Done).
2. **Fork** the repository (or create a branch if you have write access) and branch from `main`: `feat/<topic>`, `fix/<topic>`, `docs/<topic>`.
3. Make focused commits (conventional style: `feat(plan): …`, `fix(auth): …`, `docs: …`).
4. Run the checks locally:
   ```sh
   .venv/bin/ruff check . && .venv/bin/pytest -q && docker compose config -q
   ```
   UI journey tests (Playwright, Chromium, 390 px screen) run separately; `pytest -q` skips them:
   ```sh
   .venv/bin/pip install -r requirements-e2e.txt && .venv/bin/playwright install chromium   # once (CHROMIUM_PATH=/path/to/chrome reuses an installed browser)
   .venv/bin/pytest tests/e2e          # ~15 s: scripts/demo_server.py data, in-memory storage, fake LLM (tests/e2e/serve.py), no network
   scripts/lint-js.sh                  # eslint (pinned, via npx; Node 20+): undefined variables and redeclared functions in app/static/*.js
   ```
   A JavaScript error on any screen fails a journey. Write waits with `expect(...)` (auto-waiting), never fixed sleeps; one journey per file in `tests/e2e/`. CI runs both as the jobs "UI journeys" and "JS static check".
5. **Open a pull request** against `main` using the template. Link the issue (`Closes #123`). Keep it to one concern.
6. CI must be green and at least one maintainer review is required. Address comments with new commits; we squash-merge.

## What makes a good change

- Tests for the new behaviour **and** a failure case.
- Docs and `CHANGELOG.md` updated (CI checks the changelog; maintainers release as described in [docs/releasing.md](docs/releasing.md)).
- Follows [AGENTS.md](AGENTS.md) (rules of the project) — they apply to humans too.
- Rules and publications follow the recipes in [`skills/`](skills/): an ID, an evidence level, a verified source, a test.
- No secrets, personal data, real health data, IPs or private domains in code, tests, screenshots or logs.

## Using AI assistants

Welcome — the repository ships [`AGENTS.md`](AGENTS.md) and [`skills/`](skills/) for that. You remain responsible for what you submit: read the diff, run the tests, verify any citation and any model identifier yourself. Say so in the PR if a large part was generated.

## Reporting bugs / proposing features

Use the issue forms. For security issues **do not** open an issue: see [SECURITY.md](SECURITY.md). Never paste real personal health data.

## Licence

By contributing you agree that your contribution is licensed under [AGPL-3.0-only](LICENSE) like the rest of the project.

## Conduct

Be kind. See [CODE_OF_CONDUCT.md](CODE_OF_CONDUCT.md).
