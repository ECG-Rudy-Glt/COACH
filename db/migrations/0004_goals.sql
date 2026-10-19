-- Objectifs vivants : l'utilisateur peut en ajouter, modifier, terminer ou abandonner à tout moment.
CREATE TABLE IF NOT EXISTS goals (
    id          BIGSERIAL PRIMARY KEY,
    user_id     BIGINT NOT NULL REFERENCES users(id) ON DELETE CASCADE,
    title       TEXT NOT NULL,
    kind        TEXT NOT NULL DEFAULT 'other' CHECK (kind IN ('event','performance','body','health','habit','other')),
    target_date DATE,
    priority    TEXT NOT NULL DEFAULT 'important' CHECK (priority IN ('principal','important','si possible')),
    success     TEXT,
    details     JSONB NOT NULL DEFAULT '{}',
    status      TEXT NOT NULL DEFAULT 'active' CHECK (status IN ('active','done','dropped')),
    created_at  TIMESTAMPTZ NOT NULL DEFAULT now(),
    updated_at  TIMESTAMPTZ NOT NULL DEFAULT now(),
    closed_at   TIMESTAMPTZ
);
CREATE INDEX IF NOT EXISTS goals_user_idx ON goals (user_id, status, target_date);
