-- SQLite schema, equivalent to db/migrations/0001..0018 (PostgreSQL) in their final state.
-- Conventions: timestamps are ISO-8601 text in UTC (fixed width, so text order is time order),
-- dates are YYYY-MM-DD text, JSON and arrays are JSON text, booleans are 0/1 integers.
-- Ids are AUTOINCREMENT so a deleted id is never reused (like a PostgreSQL sequence).
CREATE TABLE users (
    id            INTEGER PRIMARY KEY AUTOINCREMENT,
    name          TEXT NOT NULL,
    created_at    TEXT NOT NULL,
    email         TEXT UNIQUE,
    password_hash TEXT,
    lang          TEXT CHECK (lang IN ('fr', 'en'))
);

CREATE TABLE facts (
    id            INTEGER PRIMARY KEY AUTOINCREMENT,
    user_id       INTEGER NOT NULL REFERENCES users(id) ON DELETE CASCADE,
    key           TEXT NOT NULL,
    value         TEXT NOT NULL,
    unit          TEXT,
    source        TEXT NOT NULL CHECK (source IN
                  ('questionnaire','llm_question','garmin','fit_import','manual','check_in','derived','skipped')),
    confidence    REAL NOT NULL DEFAULT 1.0 CHECK (confidence BETWEEN 0 AND 1),
    observed_at   TEXT NOT NULL,
    recorded_at   TEXT NOT NULL,
    supersedes_id INTEGER REFERENCES facts(id)
);
CREATE INDEX facts_user_key_idx ON facts (user_id, key, observed_at DESC);

CREATE TABLE exercises (
    id                INTEGER PRIMARY KEY AUTOINCREMENT,
    source            TEXT NOT NULL,
    source_id         TEXT NOT NULL,
    sources           TEXT NOT NULL DEFAULT '[]',
    name              TEXT NOT NULL,
    name_en           TEXT,
    kind              TEXT NOT NULL DEFAULT 'other',
    region            TEXT,
    muscles_primary   TEXT NOT NULL DEFAULT '[]',
    muscles_secondary TEXT NOT NULL DEFAULT '[]',
    equipment         TEXT NOT NULL DEFAULT '[]',
    level             TEXT,
    instructions      TEXT,
    instructions_lang TEXT NOT NULL DEFAULT 'fr',
    license           TEXT NOT NULL,
    license_url       TEXT,
    author            TEXT,
    UNIQUE (source, source_id)
);
CREATE INDEX exercises_name_idx ON exercises (lower(name));

CREATE TABLE exercise_media (
    id          INTEGER PRIMARY KEY AUTOINCREMENT,
    exercise_id INTEGER NOT NULL REFERENCES exercises(id) ON DELETE CASCADE,
    kind        TEXT NOT NULL CHECK (kind IN ('image', 'video')),
    url         TEXT NOT NULL,
    thumb_url   TEXT,
    is_main     INTEGER NOT NULL DEFAULT 0,
    license     TEXT NOT NULL,
    license_url TEXT,
    author      TEXT
);
CREATE INDEX exercise_media_ex_idx ON exercise_media (exercise_id);

CREATE TABLE sessions (
    token_hash TEXT PRIMARY KEY,
    user_id    INTEGER NOT NULL REFERENCES users(id) ON DELETE CASCADE,
    created_at TEXT NOT NULL,
    expires_at TEXT NOT NULL
);
CREATE INDEX sessions_user_idx ON sessions (user_id);

CREATE TABLE goals (
    id          INTEGER PRIMARY KEY AUTOINCREMENT,
    user_id     INTEGER NOT NULL REFERENCES users(id) ON DELETE CASCADE,
    title       TEXT NOT NULL,
    kind        TEXT NOT NULL DEFAULT 'other' CHECK (kind IN ('event','performance','body','health','habit','other')),
    target_date TEXT,
    priority    TEXT NOT NULL DEFAULT 'important' CHECK (priority IN ('principal','important','si possible')),
    success     TEXT,
    details     TEXT NOT NULL DEFAULT '{}',
    status      TEXT NOT NULL DEFAULT 'active' CHECK (status IN ('active','done','dropped')),
    created_at  TEXT NOT NULL,
    updated_at  TEXT NOT NULL,
    closed_at   TEXT
);
CREATE INDEX goals_user_idx ON goals (user_id, status, target_date);

CREATE TABLE planned_sessions (
    id           INTEGER PRIMARY KEY AUTOINCREMENT,
    user_id      INTEGER NOT NULL REFERENCES users(id) ON DELETE CASCADE,
    day          TEXT NOT NULL,
    kind         TEXT NOT NULL,
    title        TEXT NOT NULL,
    duration_min INTEGER NOT NULL,
    details      TEXT NOT NULL DEFAULT '{}',
    rules        TEXT NOT NULL DEFAULT '[]',
    notes        TEXT NOT NULL DEFAULT '[]',
    status       TEXT NOT NULL DEFAULT 'planned' CHECK (status IN ('planned','done','skipped')),
    logged       TEXT,
    created_at   TEXT NOT NULL,
    updated_at   TEXT NOT NULL
);
CREATE INDEX planned_user_day_idx ON planned_sessions (user_id, day);

CREATE TABLE garmin_accounts (
    user_id       INTEGER PRIMARY KEY REFERENCES users(id) ON DELETE CASCADE,
    email         TEXT NOT NULL,
    tokens_enc    TEXT NOT NULL,
    connected_at  TEXT NOT NULL,
    last_sync_at  TEXT,
    last_error    TEXT,
    backfilled_at TEXT
);

CREATE TABLE garmin_activities (
    user_id       INTEGER NOT NULL REFERENCES users(id) ON DELETE CASCADE,
    garmin_id     TEXT NOT NULL,
    day           TEXT NOT NULL,
    started_at    TEXT,
    sport         TEXT NOT NULL,
    type_key      TEXT,
    name          TEXT,
    duration_s    INTEGER,
    distance_m    REAL,
    elevation_m   REAL,
    avg_hr        INTEGER,
    max_hr        INTEGER,
    calories      INTEGER,
    training_load REAL,
    source        TEXT NOT NULL DEFAULT 'garmin',
    PRIMARY KEY (user_id, garmin_id)
);
CREATE INDEX garmin_act_day_idx ON garmin_activities (user_id, day DESC);

CREATE TABLE garmin_metrics (
    user_id INTEGER NOT NULL REFERENCES users(id) ON DELETE CASCADE,
    day     TEXT NOT NULL,
    metric  TEXT NOT NULL,
    value   REAL,
    text    TEXT,
    PRIMARY KEY (user_id, metric, day)
);

-- No latitude/longitude: the GPS track is never kept. Deleted with the activity (or the account) by cascade.
CREATE TABLE activity_streams (
    user_id    INTEGER NOT NULL REFERENCES users(id) ON DELETE CASCADE,
    garmin_id  TEXT NOT NULL,
    n          INTEGER NOT NULL,
    duration_s INTEGER NOT NULL,
    t          TEXT NOT NULL,
    dist       TEXT,
    hr         TEXT,
    speed      TEXT,
    alt        TEXT,
    cad        TEXT,
    power      TEXT,
    splits     TEXT NOT NULL DEFAULT '{}',
    created_at TEXT NOT NULL,
    PRIMARY KEY (user_id, garmin_id),
    FOREIGN KEY (user_id, garmin_id) REFERENCES garmin_activities (user_id, garmin_id) ON DELETE CASCADE
);

CREATE TABLE coach_memory (
    id           INTEGER PRIMARY KEY AUTOINCREMENT,
    user_id      INTEGER NOT NULL REFERENCES users(id) ON DELETE CASCADE,
    kind         TEXT NOT NULL CHECK (kind IN
                 ('weekly_review','advice','decision','period_summary','intake','replan_week','replan_explain','chat_adjust','absence')),
    period_start TEXT,
    period_end   TEXT,
    body         TEXT NOT NULL,
    data         TEXT NOT NULL DEFAULT '{}',
    created_at   TEXT NOT NULL
);
CREATE INDEX coach_memory_user_idx ON coach_memory (user_id, created_at DESC);

CREATE TABLE llm_calls (
    id            INTEGER PRIMARY KEY AUTOINCREMENT,
    user_id       INTEGER REFERENCES users(id) ON DELETE SET NULL,
    kind          TEXT NOT NULL,
    model         TEXT NOT NULL,
    input_tokens  INTEGER NOT NULL DEFAULT 0,
    output_tokens INTEGER NOT NULL DEFAULT 0,
    cost_eur      REAL NOT NULL DEFAULT 0,
    ok            INTEGER NOT NULL DEFAULT 1,
    error         TEXT,
    created_at    TEXT NOT NULL
);
CREATE INDEX llm_calls_month_idx ON llm_calls (created_at);

CREATE TABLE coach_messages (
    id         INTEGER PRIMARY KEY AUTOINCREMENT,
    user_id    INTEGER NOT NULL REFERENCES users(id) ON DELETE CASCADE,
    role       TEXT NOT NULL CHECK (role IN ('user','assistant')),
    body       TEXT NOT NULL,
    meta       TEXT NOT NULL DEFAULT '{}',
    created_at TEXT NOT NULL
);
CREATE INDEX coach_messages_user_idx ON coach_messages (user_id, id DESC);

CREATE TABLE notify_prefs (
    user_id       INTEGER PRIMARY KEY REFERENCES users(id) ON DELETE CASCADE,
    ntfy_topic    TEXT,
    email         TEXT,
    push_enabled  INTEGER NOT NULL DEFAULT 0,
    email_enabled INTEGER NOT NULL DEFAULT 0,
    updated_at    TEXT NOT NULL
);

CREATE TABLE notify_log (
    id         INTEGER PRIMARY KEY AUTOINCREMENT,
    user_id    INTEGER NOT NULL REFERENCES users(id) ON DELETE CASCADE,
    kind       TEXT NOT NULL,
    channel    TEXT NOT NULL,
    title      TEXT NOT NULL,
    body       TEXT NOT NULL,
    ok         INTEGER NOT NULL DEFAULT 1,
    error      TEXT,
    created_at TEXT NOT NULL
);
CREATE INDEX notify_log_user_idx ON notify_log (user_id, kind, id DESC);

CREATE TABLE push_subscriptions (
    id         INTEGER PRIMARY KEY AUTOINCREMENT,
    user_id    INTEGER NOT NULL REFERENCES users(id) ON DELETE CASCADE,
    endpoint   TEXT NOT NULL UNIQUE,
    p256dh     TEXT NOT NULL,
    auth       TEXT NOT NULL,
    created_at TEXT NOT NULL
);
CREATE INDEX push_sub_user_idx ON push_subscriptions (user_id);

CREATE TABLE meals (
    id          INTEGER PRIMARY KEY AUTOINCREMENT,
    user_id     INTEGER NOT NULL REFERENCES users(id) ON DELETE CASCADE,
    day         TEXT NOT NULL,
    slot        TEXT NOT NULL CHECK (slot IN ('petit-déjeuner','déjeuner','dîner','collation')),
    description TEXT NOT NULL DEFAULT '',
    photo_path  TEXT,
    analysis    TEXT,
    created_at  TEXT NOT NULL
);
CREATE INDEX meals_user_day_idx ON meals (user_id, day);

CREATE TABLE weight_log (
    user_id  INTEGER NOT NULL REFERENCES users(id) ON DELETE CASCADE,
    day      TEXT NOT NULL,
    kg       REAL NOT NULL CHECK (kg BETWEEN 30 AND 250),
    waist_cm REAL CHECK (waist_cm BETWEEN 40 AND 200),
    PRIMARY KEY (user_id, day)
);
