---
name: add-activity-source
description: Ingest workouts or daily metrics from a new wearable or service (Coros, Suunto, Polar, Wahoo, Strava, intervals.icu, FIT/TCX/GPX files) into COACH. Use when asked for a new data connection.
---

# Add an activity source

Read `docs/integrations.md` first. Everything downstream reads normalized rows through `Repo`, so a source only has to **produce the same rows** as `app/garmin/client.py:normalize`.

## Choose the route
1. **File import (FIT/TCX/GPX)** — works for every brand, no credentials. Prefer this.
2. **Aggregator OAuth** (Strava, intervals.icu) — pull model, tokens to encrypt.
3. **Vendor API** — only if it is public/official. No reverse-engineered logins in core.

## Steps
1. `app/<source>/client.py`: network/file I/O in a thin class; **pure** `parse_*` functions that turn raw payloads into activity rows (`garmin_id` = stable per-user id, `sport` ∈ run|bike|strength|walk|swim|other, unknown → `None` not `0`) and metric rows.
2. Storage: for credentials add a migration (see `add-migration`) with an encrypted token column using `app/garmin/crypto.py`; add `Repo` methods to the protocol, `MemoryRepo` and `PostgresRepo`. For files, dedupe on (user, id) via `upsert_activities` so re-uploading is idempotent.
3. `app/<source>/api.py`: `build_router(get_repo, require_user)`; routes for status, connect/upload, sync, disconnect(+purge). Upload endpoints: size cap, content sniffing, no path from user input.
4. Mount in `app/main.py`. Background sync: copy `app/garmin/scheduler.py` (env switch, one thread, swallow per-user errors, never log secrets).
5. Reuse `sync_user`’s tail: `_derive_facts`, `_auto_complete` (matching). Do not fork matching logic.
6. UI: a card in the connections area of `app/static/app.js`, mirroring Garmin’s (status, last sync, error, disconnect/purge).
7. Tests: parsing fixtures (anonymised real exports), unauthorized/other-user access, malformed file, rate-limit, idempotent re-sync.
8. Docs: section in `docs/integrations.md`; new dependency → `THIRD_PARTY.md` with license; ToS caveat.

## Pitfalls
- Time zones: store local start time for `day`; FIT timestamps are UTC.
- Treadmill/indoor activities have no distance/elevation: keep `None`.
- Strength sessions imported from a watch have no sets/reps — never invent them.
- Be polite to remote APIs (pauses, backoff) and cap the backfill window (`HISTORY_DAYS`).

## Verify
Upload/sync twice → same row count; a planned session of the same day/sport becomes `done` without overwriting user-typed fields.
