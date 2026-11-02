-- Périodes d'absence (G20) : la trace annulable est rangée dans coach_memory, comme les replanifications.
ALTER TABLE coach_memory DROP CONSTRAINT IF EXISTS coach_memory_kind_check;
ALTER TABLE coach_memory ADD CONSTRAINT coach_memory_kind_check
    CHECK (kind IN ('weekly_review','advice','decision','period_summary','intake','replan_week','replan_explain','chat_adjust','absence'));
