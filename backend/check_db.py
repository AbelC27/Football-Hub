try:
    from backend.database import SessionLocal
    from backend.models import League, Team, Match
except ImportError:
    from database import SessionLocal
    from models import League, Team, Match

db = SessionLocal()

print("=== LEAGUES ===")
leagues = db.query(League).all()
for league in leagues:
    print(f"ID: {league.id}, Name: {league.name}, Country: {league.country}")

print("\n=== TEAMS ===")
teams = db.query(Team).all()
for team in teams:
    print(f"ID: {team.id}, Name: {team.name}, League ID: {team.league_id}")

print("\n=== MATCHES ===")
matches = db.query(Match).limit(10).all()
for match in matches:
    print(f"ID: {match.id}, Home: {match.home_team_id}, Away: {match.away_team_id}, Status: {match.status}")

db.close()
