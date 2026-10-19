---
name: add-migration
description: Change the PostgreSQL schema of COACH with a forward-only migration and matching Repo methods for both the in-memory and Postgres repositories.
---

# Add a migration

## Steps
1. New file `db/migrations/00NN_<topic>.sql` (next number, never edit an applied file). Use `CREATE TABLE IF NOT EXISTS`, `ADD COLUMN IF NOT EXISTS`; every per-user table has `user_id BIGINT REFERENCES users(id) ON DELETE CASCADE` and an index matching its main query.
2. Keep migrations idempotent and additive; destructive changes need an explicit data-migration plan and a CHANGELOG note (users self-host and upgrade by `docker compose up -d --build`).
3. Add methods to the `Repo` protocol in `app/repo.py`, implement them in **MemoryRepo** (dict-based) **and PostgresRepo** (`psycopg`, parameterised SQL only).
4. Tests: behaviour on `MemoryRepo` in the normal suite; `tests/test_postgres.py` for the SQL (runs when `TEST_DATABASE_URL` is set).
5. Privacy: if the table holds personal data, keep the `ON DELETE CASCADE` so deleting a user removes it, and mention it in `DISCLAIMER.md` (data we store).

## Pitfalls
- Never string-format SQL.
- Migrations run at start-up in every container that calls `repo.migrate` (app and importer): they must be safe to run concurrently or in sequence.
- Store timestamps as `TIMESTAMPTZ` unless you really mean a local wall-clock time (workouts use local `DATE`/`TIMESTAMP` on purpose).

## Verify
Fresh DB: `docker compose down -v && docker compose up -d --build`. Existing DB: restart and confirm the app boots and old data is intact.
