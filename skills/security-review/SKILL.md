---
name: security-review
description: Security checklist for reviewing a COACH change (auth, routes, uploads, outbound requests, secrets, prompts, containers). Use before merging anything that touches those areas.
---

# Security review checklist

Go through the diff and answer each applicable line. Anything “no” is a blocker or needs an explicit, documented reason.

## Access control
- [ ] Every new `/users/{id}/…` route uses `require_user`; no route returns data keyed only by a client-provided id.
- [ ] Queries filter by `user_id`; list endpoints can’t be paged into other users’ rows.
- [ ] No new public route besides health/version/auth. `/docs` stays off by default.

## Input & output
- [ ] Pydantic limits on lengths, numbers, list sizes; uploads checked by content (magic bytes), size-capped, stored under generated names.
- [ ] SQL parameterised. No `eval`/`exec`/`pickle`/shell with user data. No path built from user input.
- [ ] Errors don’t leak internals, SQL, tokens or other users’ data.
- [ ] Front end: no `innerHTML` with user data (use text nodes); no inline script (CSP); no new third-party origin.

## Outbound
- [ ] HTTPS, host allowlist or fixed URL, timeout, response-size cap; no user-controlled URL (SSRF).
- [ ] Credentials of third parties are never stored in clear (tokens encrypted with `secrets_key`); passwords are discarded after the exchange.

## Secrets
- [ ] Read via `app.config.env()` / `NAME_FILE`; absent from code, tests, fixtures, logs, prompts, docs examples.
- [ ] Logging prints exception *types*/ids, not payloads (health data counts as sensitive).

## LLM
- [ ] No identity data in the context; context fields minimal and length-capped.
- [ ] Output validated server-side; the model can’t write or exceed bounds; tools are read-only and bound to the current user.
- [ ] Cost accounted (`llm_calls`) and under the monthly cap; behaviour defined when the provider is down or unconfigured.
- [ ] User text treated as data (prompt-injection thought experiment written in the PR).

## Containers & deploy
- [ ] No new published port; DB stays on the internal network; non-root user; no extra capabilities.
- [ ] New env var documented in `docs/configuration.md` and `.env.example`; secret → file secret.
- [ ] New dependency: license checked, pinned range, `pip-audit` clean.

## Report
Write findings in the PR as: *risk · where · exploit sketch · fix*. Vulnerabilities in released code go through `SECURITY.md`, not a public issue.
