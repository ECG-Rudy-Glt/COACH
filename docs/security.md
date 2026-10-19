# Security model

COACH stores health data (body metrics, training, meals, optionally Garmin data). This page lists what protects it, what does not, and how to harden an install. To report a vulnerability, see [SECURITY.md](../SECURITY.md).

## Threat model

| In scope | Out of scope |
|---|---|
| Remote attacker reaching the login page | Compromise of the host OS or Docker daemon |
| One authenticated user trying to read another's data | A malicious server administrator (they own the database) |
| Cross-site request forgery / XSS against a logged-in user | Physical access to an unlocked phone |
| Leaked backups or logs | Vulnerabilities inside your LLM provider or Garmin |
| Abuse of the LLM budget | |

## What is implemented

**Authentication & sessions**
- Passwords hashed with scrypt (N=2¹⁵, r=8, p=1, 16-byte random salt), constant-time comparison; minimum 10 characters; a password equal to the e-mail is refused.
- Session token = 256-bit random value; only its SHA-256 is stored. Cookie: `HttpOnly`, `SameSite=Lax`, `Secure` over HTTPS, 30-day lifetime. Changing the password revokes the other sessions.
- Login throttling: 5 failures / 15 min per (client IP, e-mail) and 20 per e-mail across all addresses (distributed guessing). Unknown e-mails cost the same time as wrong passwords (no user enumeration by timing).
- Registration is `first` by default: open only until the first account exists.

**Access control**
- Every `/users/{id}/…` route checks that the path id is the session's user (`require_user`); there is no shared or admin data path. Tests assert cross-user reads are refused.

**Web hardening** (`app/main.py`)
- Content-Security-Policy without inline scripts, `frame-ancestors 'none'`, `base-uri 'none'`, `object-src 'none'`; `X-Content-Type-Options`, `X-Frame-Options`, `Referrer-Policy`, `Permissions-Policy`, COOP; HSTS when served over HTTPS.
- State-changing requests carrying an `Origin` different from `Host` are rejected (on top of `SameSite`).
- `/docs` and `/openapi.json` are off unless `ENABLE_DOCS=1`.
- Optional `ALLOWED_HOSTS` rejects unexpected `Host` headers.
- Client IP from `X-Forwarded-For` is trusted only when `TRUST_PROXY=1`.

**Inputs & outbound requests**
- Meal photos: magic-byte check (JPEG/PNG only), 3 MB cap, per-day quotas. Exercise-image proxy: HTTPS only and a fixed host allowlist (no SSRF), size-capped, extension-checked.
- All SQL is parameterised.

**Secrets & data at rest**
- Secrets are files (`NAME_FILE`), never in the image, repository or process environment of other services.
- Garmin: your Garmin *password is never stored*; only the session tokens, encrypted with Fernet (`secrets_key`).
- Optional: encrypt the database volume / disk (LUKS, ZFS, cloud volume encryption) — COACH does not encrypt Postgres itself.

**Containers**
- App runs as UID 10001, read-only root filesystem, all Linux capabilities dropped, `no-new-privileges`, memory limit. The database lives on an **internal** Docker network.

**LLM**
- Identity (name, e-mail) is not sent; the context is a server-built JSON snapshot. Read-only tools only. Output is validated before anything changes; a monthly budget cap bounds spend; every call is logged (`llm_calls`).

## Known limitations

- No two-factor authentication yet (tracked in the issue board). Put the app behind a VPN or an access proxy if that matters to you.
- Login throttling is in-memory per process: it resets on restart and is not shared between replicas (COACH is designed as a single instance).
- CSP allows inline *styles* (the UI sets some style attributes).
- Sessions last 30 days and there is no "see my devices" screen yet.
- The Garmin library is unofficial; its login flow can break or be rate-limited by Garmin. Review Garmin's terms of use before enabling it.
- Backups made by the `backup` profile are plain `pg_dump` files: encrypt them if they leave the host.
- A third-party LLM provider receives the context you configure (training data, weight, goals, pain notes…). Use `ollama`/a self-hosted model if that is unacceptable.

## Hardening checklist

1. VPN-only access ([exposure.md](exposure.md) option A) — or a tunnel with an access layer in front.
2. `REGISTRATION=first` or `closed`; `ALLOWED_HOSTS`, `COOKIE_SECURE=1`, `TRUST_PROXY` set correctly.
3. Host firewall allows only what the chosen exposure needs; the database port is never published (it is not, by default).
4. Disk encryption and encrypted off-site backups; test a restore.
5. Keep images current: `docker compose pull && docker compose up -d --build`; watch the repository's Dependabot / `pip-audit` results.
6. Restrict `secrets/` (directory `700`), keep it out of cloud-synced folders and out of git (the `.gitignore` already does).
7. Set `LLM_MONTHLY_BUDGET_EUR` low and use a provider key that has its own spend limit.
8. Review `docker compose logs app` after exposing it: repeated 401/429 on `/auth/login` is normal background noise; investigate anything else.

## Reviewing a change for security

`skills/security-review/SKILL.md` contains a checklist for contributors and AI assistants: per-user isolation on new routes, no secret in logs/prompts, input limits, outbound allowlists, prompt-injection handling for user text sent to the LLM.
