-- Connexion Garmin par utilisateur : jeton chiffré (le mot de passe n'est jamais stocké) et activités importées.
CREATE TABLE IF NOT EXISTS garmin_accounts (
    user_id      BIGINT PRIMARY KEY REFERENCES users(id) ON DELETE CASCADE,
    email        TEXT NOT NULL,
    tokens_enc   TEXT NOT NULL,
    connected_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    last_sync_at TIMESTAMPTZ,
    last_error   TEXT
);

CREATE TABLE IF NOT EXISTS garmin_activities (
    user_id      BIGINT NOT NULL REFERENCES users(id) ON DELETE CASCADE,
    garmin_id    TEXT NOT NULL,
    day          DATE NOT NULL,
    started_at   TIMESTAMP,
    sport        TEXT NOT NULL,
    type_key     TEXT,
    name         TEXT,
    duration_s   INT,
    distance_m   REAL,
    elevation_m  REAL,
    avg_hr       INT,
    max_hr       INT,
    calories     INT,
    training_load REAL,
    PRIMARY KEY (user_id, garmin_id)
);
CREATE INDEX IF NOT EXISTS garmin_act_day_idx ON garmin_activities (user_id, day DESC);
