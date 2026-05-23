-- Pre-match Elo ratings per team. Each row captures the Elo of a team
-- *before* a given fixture, so feature lookup at training/inference time
-- never leaks the result of the same match.
--
-- Idempotent: safe to re-run.

CREATE TABLE IF NOT EXISTS team_elo_snapshots (
    id              SERIAL PRIMARY KEY,
    team_id         INTEGER NOT NULL,
    match_id        INTEGER NOT NULL,
    pre_match_elo   DOUBLE PRECISION NOT NULL,
    post_match_elo  DOUBLE PRECISION NOT NULL,
    is_home         BOOLEAN NOT NULL,
    snapshot_at     TIMESTAMP NOT NULL,
    CONSTRAINT uq_team_elo_match UNIQUE (team_id, match_id)
);

CREATE INDEX IF NOT EXISTS ix_team_elo_team_time ON team_elo_snapshots (team_id, snapshot_at);
CREATE INDEX IF NOT EXISTS ix_team_elo_match ON team_elo_snapshots (match_id);
