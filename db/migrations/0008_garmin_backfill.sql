-- Historique Garmin de 2 ans : date de la récupération initiale complète (NULL = à faire).
ALTER TABLE garmin_accounts ADD COLUMN IF NOT EXISTS backfilled_at TIMESTAMPTZ;
