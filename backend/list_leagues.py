from database import SessionLocal
from models import League, Team

db = SessionLocal()
print("All Leagues:")
for league in db.query(League).all():
    team_count = db.query(Team).filter(Team.league_id == league.id).count()
    print(f"  {league.name} (ID: {league.id}) - {team_count} teams")
    
db.close()
