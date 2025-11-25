"""
Database Migration Script: Add Match Events and Statistics
Run this script to update the database schema with new tables
"""

from database import engine, Base
from models import League, Team, Player, Match, Prediction, MatchEvent, MatchStatistics

def migrate_database():
    print("Creating new tables...")
    
    # Create all tables (will only create tables that don't exist)
    Base.metadata.create_all(bind=engine)
    
    print("✅ Migration complete!")
    print("New tables created:")
    print("  - match_events")
    print("  - match_statistics")

if __name__ == "__main__":
    migrate_database()
