-- 2026_05_fpl_player_signals.sql
--
-- Adds FPL-derived signal columns to `players` so we can compute a richer
-- overall rating without re-pulling bootstrap-static on every page load.
--
-- Idempotent: safe to re-run.

BEGIN;

ALTER TABLE players ADD COLUMN IF NOT EXISTS fpl_total_points    INTEGER;
ALTER TABLE players ADD COLUMN IF NOT EXISTS fpl_points_per_game DOUBLE PRECISION;
ALTER TABLE players ADD COLUMN IF NOT EXISTS fpl_form            DOUBLE PRECISION;
ALTER TABLE players ADD COLUMN IF NOT EXISTS fpl_ict_index       DOUBLE PRECISION;
ALTER TABLE players ADD COLUMN IF NOT EXISTS fpl_influence       DOUBLE PRECISION;
ALTER TABLE players ADD COLUMN IF NOT EXISTS fpl_creativity      DOUBLE PRECISION;
ALTER TABLE players ADD COLUMN IF NOT EXISTS fpl_threat          DOUBLE PRECISION;
ALTER TABLE players ADD COLUMN IF NOT EXISTS fpl_element_type    INTEGER;

COMMIT;
