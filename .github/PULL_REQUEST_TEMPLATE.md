## What and why
<!-- One paragraph. Link the issue: Closes #… -->

## How I tested
<!-- Commands run, scenarios tried, screenshots for UI (no real personal data). -->

## Checklist
- [ ] `ruff check .` and `pytest -q` pass; new behaviour has tests (incl. a failure case)
- [ ] Docs / `CHANGELOG.md` updated
- [ ] Follows `AGENTS.md` (rules in the engine, per-user isolation, no secrets, no identity to LLM)
- [ ] Touches auth, routes, uploads, outbound requests, prompts or containers → `skills/security-review` applied
- [ ] Rule/publication changes include ID, evidence level and a verified source
- [ ] No secrets, IPs, private domains or real health data in the diff
- [ ] AI-assisted? I reviewed the output and verified citations and model IDs
