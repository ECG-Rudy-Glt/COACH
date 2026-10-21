-- Source des activités (garmin par défaut ; fit, tcx, gpx pour les fichiers importés). L'identifiant externe reste garmin_id : « <format>:<empreinte du fichier> » pour un import.
ALTER TABLE garmin_activities ADD COLUMN IF NOT EXISTS source TEXT NOT NULL DEFAULT 'garmin';
