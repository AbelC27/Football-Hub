"""
Final database verification
"""
from database import SessionLocal
from models import League, Team, Match, Standing, Player

db = SessionLocal()

print("=" * 70)
print("FINAL DATABASE VERIFICATION")
print("=" * 70)

leagues = db.query(League).all()
print(f"\nTotal Leagues: {len(leagues)}")

total_teams = 0
total_matches = 0
total_standings = 0
total_players = 0

for league in leagues:
    teams = db.query(Team).filter(Team.league_id == league.id).count()
    matches = db.query(Match).join(Team, Match.home_team_id == Team.id).filter(Team.league_id == league.id).count()
    standings = db.query(Standing).filter(Standing.league_id == league.id).count()
    players = db.query(Player).join(Team).filter(Team.league_id == league.id).count()
    
    print(f"\n{league.name}:")
    print(f"  Teams: {teams}")
    print(f"  Standings: {standings}")
    print(f"  Matches: {matches}")
    print(f"  Players: {players}")
    
    total_teams += teams
    total_matches += matches
    total_standings += standings
    total_players += players

print("\n" + "=" * 70)
print("TOTALS:")
print(f"  Leagues: {len(leagues)}")
print(f"  Teams: {total_teams}")
print(f"  Players: {total_players}")
print(f"  Matches: {total_matches}")
print(f"  Standings: {total_standings}")
print("=" * 70)

# Check data quality
print("\nDATA QUALITY CHECKS:")
print(f"✓ Teams with players: {db.query(Team).join(Player).distinct().count()}")
print(f"✓ Matches with scores: {db.query(Match).filter(Match.home_score.isnot(None)).count()}")
print(f"✓ Leagues with standings: {db.query(League).join(Standing).distinct().count()}")

print("\n✅ Database verification complete!")
db.close()
