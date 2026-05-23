"""One-shot script to (re)build the team_elo_snapshots table from scratch.

Walks every finished match in chronological order, replays the EloEngine
on it and stores both the pre-match and post-match rating for each team.
The result is the ground truth used by the training pipeline:

- For any historical match, the feature `home_elo_pre` is read directly
  from `team_elo_snapshots` -> guaranteed leakage-free.
- For any future match, we look up the *latest* `post_match_elo` for each
  team and feed it as the `*_elo_pre` of that fixture.

Re-run safely whenever new finished matches arrive: the table is
truncated and rebuilt from scratch (cheap, ~2k matches in our dataset).
"""

from __future__ import annotations

import os
import sys
from datetime import datetime

sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from sqlalchemy import text  # noqa: E402

try:
    from backend.ai.elo import EloEngine, EloMatchInput
    from backend.database import SessionLocal
    from backend.models import Match, TeamEloSnapshot
except ImportError:
    from ai.elo import EloEngine, EloMatchInput  # type: ignore[no-redef]
    from database import SessionLocal  # type: ignore[no-redef]
    from models import Match, TeamEloSnapshot  # type: ignore[no-redef]


FINISHED_STATUSES = {"FT", "AET", "PEN"}


def main() -> None:
    db = SessionLocal()
    try:
        # Wipe and rebuild from scratch. Cheaper than incremental updates
        # at our scale and avoids tricky ordering bugs around late-arriving
        # finished matches.
        db.execute(text("DELETE FROM team_elo_snapshots"))
        db.commit()

        finished = (
            db.query(Match)
            .filter(Match.status.in_(FINISHED_STATUSES))
            .filter(Match.home_score.isnot(None))
            .filter(Match.away_score.isnot(None))
            .order_by(Match.start_time.asc(), Match.id.asc())
            .all()
        )
        print(f"Replaying Elo over {len(finished)} finished matches...")

        engine = EloEngine()
        snapshots = []

        for match in finished:
            update = engine.update_from_match(
                EloMatchInput(
                    match_id=match.id,
                    home_team_id=match.home_team_id,
                    away_team_id=match.away_team_id,
                    home_score=match.home_score,
                    away_score=match.away_score,
                )
            )
            snapshot_at = match.start_time or datetime.utcnow()

            snapshots.append(
                TeamEloSnapshot(
                    team_id=match.home_team_id,
                    match_id=match.id,
                    pre_match_elo=update.home_pre,
                    post_match_elo=update.home_post,
                    is_home=True,
                    snapshot_at=snapshot_at,
                )
            )
            snapshots.append(
                TeamEloSnapshot(
                    team_id=match.away_team_id,
                    match_id=match.id,
                    pre_match_elo=update.away_pre,
                    post_match_elo=update.away_post,
                    is_home=False,
                    snapshot_at=snapshot_at,
                )
            )

        # Insert in chunks so we don't overwhelm the Supabase pooler with
        # one giant INSERT.
        batch_size = 500
        for i in range(0, len(snapshots), batch_size):
            db.bulk_save_objects(snapshots[i : i + batch_size])
            db.commit()

        ratings = engine.snapshot()
        top10 = sorted(ratings.items(), key=lambda kv: kv[1], reverse=True)[:10]
        print(f"\nFinal Elo top 10 (out of {len(ratings)} teams):")
        for team_id, rating in top10:
            print(f"  team_id={team_id}  elo={rating:.1f}")

        print(f"\nPersisted {len(snapshots)} snapshots.")
    finally:
        db.close()


if __name__ == "__main__":
    main()
