-- Discussion avec le coach, préférences de notification (push ntfy, mail) et journal des envois.
CREATE TABLE IF NOT EXISTS coach_messages (
    id         BIGSERIAL PRIMARY KEY,
    user_id    BIGINT NOT NULL REFERENCES users(id) ON DELETE CASCADE,
    role       TEXT NOT NULL CHECK (role IN ('user','assistant')),
    body       TEXT NOT NULL,
    meta       JSONB NOT NULL DEFAULT '{}',
    created_at TIMESTAMPTZ NOT NULL DEFAULT now()
);
CREATE INDEX IF NOT EXISTS coach_messages_user_idx ON coach_messages (user_id, id DESC);

CREATE TABLE IF NOT EXISTS notify_prefs (
    user_id       BIGINT PRIMARY KEY REFERENCES users(id) ON DELETE CASCADE,
    ntfy_topic    TEXT,
    email         TEXT,
    push_enabled  BOOLEAN NOT NULL DEFAULT false,
    email_enabled BOOLEAN NOT NULL DEFAULT false,
    updated_at    TIMESTAMPTZ NOT NULL DEFAULT now()
);

CREATE TABLE IF NOT EXISTS notify_log (
    id         BIGSERIAL PRIMARY KEY,
    user_id    BIGINT NOT NULL REFERENCES users(id) ON DELETE CASCADE,
    kind       TEXT NOT NULL,
    channel    TEXT NOT NULL,
    title      TEXT NOT NULL,
    body       TEXT NOT NULL,
    ok         BOOLEAN NOT NULL DEFAULT true,
    error      TEXT,
    created_at TIMESTAMPTZ NOT NULL DEFAULT now()
);
CREATE INDEX IF NOT EXISTS notify_log_user_idx ON notify_log (user_id, kind, id DESC);
