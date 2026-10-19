-- Bibliothèque d'exercices : fusion de wger (CC), free-exercise-db (domaine public) et exercices maison.
-- Chaque exercice et chaque média garde sa licence et son auteur (affichés dans l'app).
CREATE TABLE IF NOT EXISTS exercises (
    id               BIGSERIAL PRIMARY KEY,
    source           TEXT NOT NULL,
    source_id        TEXT NOT NULL,
    sources          TEXT[] NOT NULL DEFAULT '{}',
    name             TEXT NOT NULL,
    name_en          TEXT,
    kind             TEXT NOT NULL DEFAULT 'other',
    region           TEXT,
    muscles_primary  TEXT[] NOT NULL DEFAULT '{}',
    muscles_secondary TEXT[] NOT NULL DEFAULT '{}',
    equipment        TEXT[] NOT NULL DEFAULT '{}',
    level            TEXT,
    instructions     TEXT,
    instructions_lang TEXT NOT NULL DEFAULT 'fr',
    license          TEXT NOT NULL,
    license_url      TEXT,
    author           TEXT,
    UNIQUE (source, source_id)
);
CREATE INDEX IF NOT EXISTS exercises_name_idx ON exercises (lower(name));
CREATE INDEX IF NOT EXISTS exercises_muscles_idx ON exercises USING GIN (muscles_primary);

CREATE TABLE IF NOT EXISTS exercise_media (
    id          BIGSERIAL PRIMARY KEY,
    exercise_id BIGINT NOT NULL REFERENCES exercises(id) ON DELETE CASCADE,
    kind        TEXT NOT NULL CHECK (kind IN ('image', 'video')),
    url         TEXT NOT NULL,
    thumb_url   TEXT,
    is_main     BOOLEAN NOT NULL DEFAULT false,
    license     TEXT NOT NULL,
    license_url TEXT,
    author      TEXT
);
CREATE INDEX IF NOT EXISTS exercise_media_ex_idx ON exercise_media (exercise_id);
