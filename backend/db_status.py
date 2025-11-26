import sys
from database import SessionLocal
from models import League, Team, Standing, Match

db = SessionLocal()

print("="*60)
print("DATABASE STATUS")
print("="*60)

leagues = db.query(League).all()
print(f"\nTotal Leagues: {len(leagues)}\n")

for league in leagues:
    team_count = db.query(Team).filter(Team.league_id == league.id).count()
    standing_count = db.query(Standing).filter(Standing.league_id == league.id).count()
    
    # Count matches where teams from this league play
    match_count = db.query(Match).join(
        Team, Match.home_team_id == Team.id
    ).filter(Team.league_id == league.id).count()
    
    print(f"{league.name}:")
    print(f"  ID: {league.id}")
    print(f"  Teams: {team_count}")
    print(f"  Standings: {standing_count}")
    print(f"  Matches: {match_count}")
    print()

print("="*60)
print(f"TOTALS:")
print(f"  Teams: {db.query(Team).count()}")
print(f"  Matches: {db.query(Match).count()}")
print("="*60)

db.close()
