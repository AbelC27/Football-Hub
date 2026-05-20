-- 2026_05_apisports_integration.sql
--
-- Adds the junction table that maps local football-data.org IDs to
-- api-sports.io IDs and extends match_events with player/assist linkage.
--
-- Idempotent: safe to re-run on Postgres 9.6+.

BEGIN;

-- 1. Junction table for cross-provider ID mapping.
CREATE TABLE IF NOT EXISTS provider_id_map (
    id           SERIAL PRIMARY KEY,
    provider     VARCHAR  NOT NULL,
    entity_type  VARCHAR  NOT NULL,
    local_id     INTEGER  NOT NULL,
    external_id  INTEGER  NOT NULL,
    confidence   DOUBLE PRECISION,
    notes        VARCHAR,
    created_at   TIMESTAMP WITHOUT TIME ZONE DEFAULT (now() AT TIME ZONE 'utc'),
    updated_at   TIMESTAMP WITHOUT TIME ZONE DEFAULT (now() AT TIME ZONE 'utc')
);

-- Lookup index (provider + entity_type + local_id is the hot path).
CREATE INDEX IF NOT EXISTS ix_provider_id_map_id ON provider_id_map (id);

-- Unique constraints matching the SQLAlchemy model.
DO $$
BEGIN
    IF NOT EXISTS (
        SELECT 1 FROM pg_constraint WHERE conname = 'uq_provider_local'
    ) THEN
        ALTER TABLE provider_id_map
            ADD CONSTRAINT uq_provider_local UNIQUE (provider, entity_type, local_id);
    END IF;

    IF NOT EXISTS (
        SELECT 1 FROM pg_constraint WHERE conname = 'uq_provider_external'
    ) THEN
        ALTER TABLE provider_id_map
            ADD CONSTRAINT uq_provider_external UNIQUE (provider, entity_type, external_id);
    END IF;
END$$;

-- 2. Extend match_events with api-sports linkage. No FK constraints so we
-- don't have to worry about ingest ordering.
ALTER TABLE match_events
    ADD COLUMN IF NOT EXISTS player_id INTEGER;

ALTER TABLE match_events
    ADD COLUMN IF NOT EXISTS assist_player_id INTEGER;

ALTER TABLE match_events
    ADD COLUMN IF NOT EXISTS assist_player_name VARCHAR;

COMMIT;
