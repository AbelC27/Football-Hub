"""
Additive migration for player-based fantasy mode.

This script is non-destructive:
- Creates only missing fantasy player-mode tables.
- Does not modify or drop existing team-mode fantasy tables.
"""

from sqlalchemy import inspect

try:
    from backend.database import engine
    from backend.models import (
        FantasyMatchdayPick,
        FantasyMatchdaySummary,
        FantasyPlayerSquad,
        FantasyPointsHistory,
        FantasySquadPlayer,
        FantasyTransfer,
    )
except ImportError:
    from database import engine
    from models import (
        FantasyMatchdayPick,
        FantasyMatchdaySummary,
        FantasyPlayerSquad,
        FantasyPointsHistory,
        FantasySquadPlayer,
        FantasyTransfer,
    )


FANTASY_PLAYER_MODE_TABLES = [
    FantasyPlayerSquad.__table__,
    FantasySquadPlayer.__table__,
    FantasyMatchdayPick.__table__,
    FantasyTransfer.__table__,
    FantasyPointsHistory.__table__,
    FantasyMatchdaySummary.__table__,
]


def migrate_fantasy_player_mode() -> None:
    inspector = inspect(engine)
    existing_tables = set(inspector.get_table_names())

    missing_tables = [table for table in FANTASY_PLAYER_MODE_TABLES if table.name not in existing_tables]

    if not missing_tables:
        print("Fantasy player-mode tables already exist. No changes applied.")
        return

    print("Creating fantasy player-mode tables...")
    for table in missing_tables:
        table.create(bind=engine, checkfirst=True)
        print(f"  - created {table.name}")

    print("Fantasy player-mode migration complete.")


if __name__ == "__main__":
    migrate_fantasy_player_mode()
