-- Profil en faits datés : rien n'est écrasé, la valeur courante d'une clé est le fait
-- le plus récent non remplacé.
CREATE TABLE IF NOT EXISTS users (
    id         BIGSERIAL PRIMARY KEY,
    name       TEXT NOT NULL,
    created_at TIMESTAMPTZ NOT NULL DEFAULT now()
);

CREATE TABLE IF NOT EXISTS facts (
    id            BIGSERIAL PRIMARY KEY,
    user_id       BIGINT NOT NULL REFERENCES users(id) ON DELETE CASCADE,
    key           TEXT NOT NULL,
    value         JSONB NOT NULL,
    unit          TEXT,
    source        TEXT NOT NULL CHECK (source IN
                  ('questionnaire','llm_question','garmin','fit_import','manual','check_in','derived','skipped')),
    confidence    REAL NOT NULL DEFAULT 1.0 CHECK (confidence BETWEEN 0 AND 1),
    observed_at   TIMESTAMPTZ NOT NULL DEFAULT now(),
    recorded_at   TIMESTAMPTZ NOT NULL DEFAULT now(),
    supersedes_id BIGINT REFERENCES facts(id)
);

CREATE INDEX IF NOT EXISTS facts_user_key_idx ON facts (user_id, key, observed_at DESC);
