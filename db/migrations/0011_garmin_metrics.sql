-- Mesures quotidiennes Garmin : FC au repos, VO2max, temps estimés, statut d'entraînement et charges (une ligne par jour et par mesure).
CREATE TABLE IF NOT EXISTS garmin_metrics (
    user_id BIGINT NOT NULL REFERENCES users(id) ON DELETE CASCADE,
    day     DATE NOT NULL,
    metric  TEXT NOT NULL,
    value   REAL,
    text    TEXT,
    PRIMARY KEY (user_id, metric, day)
);
