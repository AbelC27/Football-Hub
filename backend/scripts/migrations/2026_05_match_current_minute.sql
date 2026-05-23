-- Adds the live `current_minute` column on matches.
-- Idempotent: safe to re-run.

ALTER TABLE matches
    ADD COLUMN IF NOT EXISTS current_minute INTEGER;
