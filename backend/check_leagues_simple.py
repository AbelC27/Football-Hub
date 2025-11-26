from database import SessionLocal
from models import League, Team, Match, Standing

db = SessionLocal()

print("Current Leagues in Database:")
print("-" * 50)

leagues = db.query(League).all()
for league in leagues:
    team_count = db.query(Team).filter(Team.league_id == league.id).count()
    standing_count = db.query(Standing).filter(Standing.league_id == league.id).count()
    
    # Count matches for this league
    match_count = db.query(Match).join(
        Team, Match.home_team_id == Team.id
    ).filter(Team.league_id == league.id).count()
    
    print(f"\n{league.name}")
    print(f"  ID: {league.id}")
    print(f"  Teams: {team_count}")
    print(f"  Standings: {standing_count}")
    print(f"  Matches: {match_count}")

db.close()
