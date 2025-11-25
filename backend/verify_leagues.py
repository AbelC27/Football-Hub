import sys
import os
sys.path.append(os.path.dirname(os.path.abspath(__file__)))

try:
    from database import SessionLocal
    from models import League, Team, Match, Standing
except ImportError:
    from backend.database import SessionLocal
    from backend.models import League, Team, Match, Standing

db = SessionLocal()

print("=== VERIFICATION REPORT ===")

leagues = db.query(League).all()
print(f"\nTotal Leagues: {len(leagues)}")
for l in leagues:
    teams_count = db.query(Team).filter(Team.league_id == l.id).count()
    standings_count = db.query(Standing).filter(Standing.league_id == l.id).count()
    # Matches don't have league_id directly in DB model yet (we added it to API response only), 
    # but we can check matches via teams.
    # Actually, we can just count total matches for now or check if any match exists for teams in this league.
    
    print(f"- {l.name} ({l.country}): {teams_count} teams, {standings_count} standings entries")

print("\n=== END REPORT ===")
db.close()
