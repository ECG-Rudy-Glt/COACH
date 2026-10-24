-- Replanification de la fin de semaine (G13 à G17) : la trace annulable et la phrase d'explication mémorisée sont rangées dans coach_memory.
ALTER TABLE coach_memory DROP CONSTRAINT IF EXISTS coach_memory_kind_check;
ALTER TABLE coach_memory ADD CONSTRAINT coach_memory_kind_check
    CHECK (kind IN ('weekly_review','advice','decision','period_summary','intake','replan_week','replan_explain'));
