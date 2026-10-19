# Integrations: wearables, services and features

This page explains how data gets in (Garmin today, Coros and others tomorrow), and how to add a new service or feature without breaking the project's rules. For prompts see [prompts.md](prompts.md); for AI-assisted forking see [../AGENTS.md](../AGENTS.md).

## What "ingestion" means here

A wearable integration produces two kinds of rows for a user:

| Kind | Table | Used by |
|---|---|---|
| **Activities** (a run, a ride, a strength session) | `garmin_activities` | matching with planned sessions, weekly review, history tools |
| **Daily metrics** (resting HR, VO2max, race predictions, training load…) | `garmin_metrics` | derived facts (e.g. benchmarks), coach context |

Everything downstream (`app/garmin/match.py`, `app/coach/history.py`, `service.build_context`) only reads normalized rows through the `Repo` interface, so a new source only has to *produce the same rows*.

> The tables carry the `garmin_` prefix for historical reasons. Generalising them to a `source` column is the recommended first step for a second brand — see the "Activity sources" issue on the board.

### Normalized activity row

`normalize()` in `app/garmin/client.py` is the reference. Keys:

```python
{"garmin_id": "str, unique per user (any stable id)", "day": date, "started_at": datetime,
 "sport": "run|bike|strength|walk|swim|other", "type_key": "source-specific type or None", "name": "str|None",
 "duration_s": int|None, "distance_m": float|None, "elevation_m": float|None,
 "avg_hr": int|None, "max_hr": int|None, "calories": int|None, "training_load": float|None}
```
Unknown values are `None`, never `0`. Map the brand's sport names to the six `sport` values (see `SPORTS`).

### Normalized metric row

`{"day": date, "metric": "resting_hr|vo2max|vo2max_cycling|race_5k|race_10k|race_half|race_marathon|training_status|acwr|load_acute|load_chronic|load_aerobic_low|load_aerobic_high|load_anaerobic|load_balance", "value": float|None, "text": str|None}`. New metric names must also be added to `SERIES` in `app/coach/history.py` to be searchable by the chat tools.

## Garmin (built in)

**How it works**
1. The user enters their Garmin e-mail and password (and an MFA code if enabled) in the app. `GarminGateway.start_login` uses the unofficial [`garminconnect`](https://github.com/cyberjunky/python-garminconnect) library.
2. Only the resulting **token set** is stored, encrypted with Fernet (`secrets_key`). The password is discarded.
3. `sync_user()` (`app/garmin/api.py`) runs on demand and, if `AUTO_SYNC=1`, every `GARMIN_SYNC_HOURS`: first connection backfills 730 days, later runs fetch 28 days, tokens are refreshed and re-encrypted, old rows are pruned.
4. `_auto_complete()` pairs recent activities with planned sessions (same day, compatible sport, closest duration, one activity per session) and marks them done without overwriting what the user typed.
5. Failures map to business errors (`GarminAuthError` → "reconnect", `GarminRateLimited` → 429, `GarminUnavailable` → 502); credentials never reach logs.

**Caveats** — the library is unofficial and Garmin changed its authentication in 2026; use is at your own risk and subject to Garmin's terms. Keep sync intervals polite (`SYNC_PAUSE_S`, default 2 s between users).

## Coros and other brands

Coros does not offer a public API for individual developers (its API is partner-only), so there is no password-based or OAuth connection to copy from Garmin. There are three realistic routes, from most to least robust:

1. **Activity file import (recommended).** Coros, Suunto, Polar, Wahoo, Apple Watch exports… all produce **FIT/TCX/GPX** files. A single *file-import adapter* gives every brand an entry point: upload from the phone (share sheet → COACH) or drop files in a watched folder, parse with a FIT library (`fitdecode`), `normalize` to the activity row above, `upsert_activities`. Metrics (HR, load) come from the file where present. Tracked as an issue on the board — this is the best first contribution for non-Garmin users.
2. **Aggregator bridge.** Coros → Strava (or intervals.icu, Runalyze) is officially supported by Coros; COACH then reads from the aggregator's OAuth API. The adapter shape is the same as Garmin's (`fetch_activities(tokens, start, end) -> (rows, fresh_tokens)`), but you register your own API application and handle rate limits and the aggregator's terms.
3. **Unofficial reverse-engineered clients.** Possible but fragile and against most terms of service; not accepted into the core without a clear maintenance plan.

### Adding a source — step by step

1. **Decide the shape**: pull (credentials/OAuth, background sync) or push (file upload). Write it as an adapter class in `app/<source>/client.py` with *pure* parsing functions (`parse_*`) separated from network calls, so tests use recorded fixtures.
2. **Storage**: if the source needs credentials/tokens, add a migration `db/migrations/00NN_<source>.sql` (forward-only, `IF NOT EXISTS`) for an accounts table whose token column is encrypted with `app/garmin/crypto.py` (reuse `secrets_key`). Add the methods to the `Repo` protocol **and** to both `MemoryRepo` and `PostgresRepo`.
3. **API router** `app/<source>/api.py` with `build_router(get_repo, require_user)` mounted in `app/main.py`: status, connect/upload, sync, disconnect (`purge` option). Every route depends on `require_user`.
4. **Scheduler**: reuse the pattern of `app/garmin/scheduler.py` (single thread, env switch, never log credentials, swallow per-user errors).
5. **Plumb into the existing flow**: call `repo.upsert_activities` / `upsert_metrics`, then `_derive_facts` and `_auto_complete` — do not duplicate matching logic.
6. **UI**: a card in the profile/connections screen (`app/static/app.js`, see how Garmin's is built) with status, last sync, error and a disconnect/purge button.
7. **Tests**: parsing fixtures, auth failure, per-user isolation, rate-limit handling, idempotent re-sync (no duplicate rows).
8. **Docs**: add a section here (what is stored, ToS caveat) and update `THIRD_PARTY.md` for any new dependency.

## Adding any other service (nutrition database, weather, calendar…)

Follow the same discipline: **adapter + pure parsing + Repo methods + router + tests + docs**. Extra rules that keep the project trustworthy:

- Outbound requests: HTTPS, fixed host allowlist, timeout, response-size cap, no user-controlled URLs.
- Anything the service returns that influences a *plan or target* must go through the rule engine and carry a rule ID. Do not let external data change numbers silently.
- Anything sent to an LLM must be added to the context builder deliberately (see [prompts.md](prompts.md)) and contain no identity data.
- Make it optional: the app must still start and be useful when the service is not configured.

## Adding a feature to the engine

| You want to add… | Touch | Must also |
|---|---|---|
| A questionnaire question | `questions/<domain>.yaml` | keep ids unique and conditions valid (`validate_bank` runs at start-up); add a test if it feeds a fact the engine reads |
| A training/nutrition rule | `app/plan/*`, `app/nutrition/engine.py`, `docs/rules.md`, `data/rules_digest.yaml` | give it an ID, an evidence level, and a test; the digest test checks `rules.md` ↔ `rules_digest.yaml` |
| A publication | `data/evidence/*.yaml` | verified DOI/PMID/URL, abstract-level finding, **limits**, `applies_to` rule IDs, `verified_on` |
| An LLM-callable read tool | `app/coach/history.py` (`TOOLS` + `run_tool`) | read-only, bounded output (≈6 000 chars), schema in the OpenAI/Anthropic-neutral `input_schema` form |
| A DB table | `db/migrations/` + `Repo` + both implementations | forward-only migration; `ON DELETE CASCADE` from `users` |

The `skills/` directory holds step-by-step recipes for each of these, written so a coding assistant can follow them.
