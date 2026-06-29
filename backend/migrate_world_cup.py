"""
Additive migration for FIFA World Cup 2026 support.

Adds `stage` and `group_name` columns to the `matches` table.
Non-destructive: skips columns that already exist.
"""

from sqlalchemy import text, inspect

try:
    from backend.database import engine
except ImportError:
    from database import engine


def migrate():
    inspector = inspect(engine)
    existing = {col["name"] for col in inspector.get_columns("matches")}

    with engine.begin() as conn:
        if "stage" not in existing:
            conn.execute(text("ALTER TABLE matches ADD COLUMN stage VARCHAR"))
            print("  ✓ Added column: matches.stage")
        else:
            print("  - Column matches.stage already exists")

        if "group_name" not in existing:
            conn.execute(text("ALTER TABLE matches ADD COLUMN group_name VARCHAR"))
            print("  ✓ Added column: matches.group_name")
        else:
            print("  - Column matches.group_name already exists")

    print("✅ World Cup migration complete!")


if __name__ == "__main__":
    migrate()
