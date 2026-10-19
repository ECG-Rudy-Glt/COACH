-- Mémoire du coach (bilans, propositions, conseils) et journal des appels au LLM (coût, traçabilité).
CREATE TABLE IF NOT EXISTS coach_memory (
    id           BIGSERIAL PRIMARY KEY,
    user_id      BIGINT NOT NULL REFERENCES users(id) ON DELETE CASCADE,
    kind         TEXT NOT NULL CHECK (kind IN ('weekly_review','advice','decision','period_summary')),
    period_start DATE,
    period_end   DATE,
    body         TEXT NOT NULL,
    data         JSONB NOT NULL DEFAULT '{}',
    created_at   TIMESTAMPTZ NOT NULL DEFAULT now()
);
CREATE INDEX IF NOT EXISTS coach_memory_user_idx ON coach_memory (user_id, created_at DESC);

CREATE TABLE IF NOT EXISTS llm_calls (
    id            BIGSERIAL PRIMARY KEY,
    user_id       BIGINT REFERENCES users(id) ON DELETE SET NULL,
    kind          TEXT NOT NULL,
    model         TEXT NOT NULL,
    input_tokens  INT NOT NULL DEFAULT 0,
    output_tokens INT NOT NULL DEFAULT 0,
    cost_eur      NUMERIC(10,5) NOT NULL DEFAULT 0,
    ok            BOOLEAN NOT NULL DEFAULT true,
    error         TEXT,
    created_at    TIMESTAMPTZ NOT NULL DEFAULT now()
);
CREATE INDEX IF NOT EXISTS llm_calls_month_idx ON llm_calls (created_at);
