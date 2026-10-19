-- Nutrition : repas déclarés (texte, photo facultative, estimation IA) et suivi du poids.
CREATE TABLE IF NOT EXISTS meals (
    id          BIGSERIAL PRIMARY KEY,
    user_id     BIGINT NOT NULL REFERENCES users(id) ON DELETE CASCADE,
    day         DATE NOT NULL,
    slot        TEXT NOT NULL CHECK (slot IN ('petit-déjeuner','déjeuner','dîner','collation')),
    description TEXT NOT NULL DEFAULT '',
    photo_path  TEXT,
    analysis    JSONB,
    created_at  TIMESTAMPTZ NOT NULL DEFAULT now()
);
CREATE INDEX IF NOT EXISTS meals_user_day_idx ON meals (user_id, day);

CREATE TABLE IF NOT EXISTS weight_log (
    user_id  BIGINT NOT NULL REFERENCES users(id) ON DELETE CASCADE,
    day      DATE NOT NULL,
    kg       NUMERIC(5,2) NOT NULL CHECK (kg BETWEEN 30 AND 250),
    waist_cm NUMERIC(5,1) CHECK (waist_cm BETWEEN 40 AND 200),
    PRIMARY KEY (user_id, day)
);
