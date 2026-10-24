-- Courbes simplifiées d'une activité (FC, vitesse, altitude, cadence, puissance), 300 à 500 points par activité.
-- Aucune latitude ni longitude : la trace GPS n'est jamais conservée. Supprimées avec l'activité (ou le compte) par cascade.
CREATE TABLE IF NOT EXISTS activity_streams (
    user_id     BIGINT NOT NULL REFERENCES users(id) ON DELETE CASCADE,
    garmin_id   TEXT NOT NULL,
    n           INT NOT NULL,
    duration_s  INT NOT NULL,
    t           INT[] NOT NULL,         -- secondes depuis le début
    dist        REAL[],                 -- mètres cumulés
    hr          SMALLINT[],
    speed       REAL[],                 -- m/s
    alt         REAL[],                 -- mètres
    cad         SMALLINT[],             -- pas ou tours par minute
    power       SMALLINT[],             -- watts
    splits      JSONB NOT NULL DEFAULT '{}',
    created_at  TIMESTAMPTZ NOT NULL DEFAULT now(),
    PRIMARY KEY (user_id, garmin_id),
    FOREIGN KEY (user_id, garmin_id) REFERENCES garmin_activities (user_id, garmin_id) ON DELETE CASCADE
);
