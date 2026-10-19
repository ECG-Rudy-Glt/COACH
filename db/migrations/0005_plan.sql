-- Séances planifiées (générées par le moteur) et leur réalisation. L'historique n'est jamais supprimé :
-- une régénération ne remplace que les séances encore « planned » à partir d'une date de gel.
CREATE TABLE IF NOT EXISTS planned_sessions (
    id           BIGSERIAL PRIMARY KEY,
    user_id      BIGINT NOT NULL REFERENCES users(id) ON DELETE CASCADE,
    day          DATE NOT NULL,
    kind         TEXT NOT NULL,
    title        TEXT NOT NULL,
    duration_min INT NOT NULL,
    details      JSONB NOT NULL DEFAULT '{}',
    rules        TEXT[] NOT NULL DEFAULT '{}',
    notes        TEXT[] NOT NULL DEFAULT '{}',
    status       TEXT NOT NULL DEFAULT 'planned' CHECK (status IN ('planned','done','skipped')),
    logged       JSONB,
    created_at   TIMESTAMPTZ NOT NULL DEFAULT now(),
    updated_at   TIMESTAMPTZ NOT NULL DEFAULT now()
);
CREATE INDEX IF NOT EXISTS planned_user_day_idx ON planned_sessions (user_id, day);
