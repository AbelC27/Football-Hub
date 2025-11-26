from sqlalchemy import text
from database import engine

def migrate():
    with engine.connect() as conn:
        # List of new columns and their types
        new_columns = [
            ("photo_url", "VARCHAR"),
            ("date_of_birth", "TIMESTAMP"),
            ("market_value", "VARCHAR"),
            ("jersey_number", "INTEGER"),
            ("goals_season", "INTEGER"),
            ("assists_season", "INTEGER"),
            ("rating_season", "FLOAT"),
            ("minutes_played", "INTEGER")
        ]
        
        for col_name, col_type in new_columns:
            try:
                # Try to add the column. If it exists, it will fail, which we catch.
                # Note: This syntax works for PostgreSQL. For SQLite it might be slightly different but usually ADD COLUMN is supported.
                conn.execute(text(f"ALTER TABLE players ADD COLUMN {col_name} {col_type}"))
                print(f"Added column {col_name}")
            except Exception as e:
                print(f"Column {col_name} might already exist or error: {e}")
                
        conn.commit()

if __name__ == "__main__":
    print("Migrating database...")
    migrate()
    print("Migration complete.")
