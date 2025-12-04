"""
Remove Copa Libertadores from database
"""
from database import SessionLocal
from models import League, Team, Match, Standing, Player

db = SessionLocal()

# Find Copa Libertadores
copa = db.query(League).filter(League.id == 2152).first()

if copa:
    print(f"Found: {copa.name} (ID: {copa.id})")
    
    # Delete all related data
    # 1. Delete standings
    standings_deleted = db.query(Standing).filter(Standing.league_id == copa.id).delete()
    print(f"Deleted {standings_deleted} standings")
    
    # 2. Get team IDs from this league
    copa_teams = db.query(Team).filter(Team.league_id == copa.id).all()
    copa_team_ids = [t.id for t in copa_teams]
    print(f"Found {len(copa_team_ids)} teams")
    
    # 3. Delete players from these teams
    players_deleted = db.query(Player).filter(Player.team_id.in_(copa_team_ids)).delete(synchronize_session=False)
    print(f"Deleted {players_deleted} players")
    
    # 4. Delete matches involving these teams
    matches_deleted = db.query(Match).filter(
        (Match.home_team_id.in_(copa_team_ids)) | (Match.away_team_id.in_(copa_team_ids))
    ).delete(synchronize_session=False)
    print(f"Deleted {matches_deleted} matches")
    
    # 5. Delete teams
    teams_deleted = db.query(Team).filter(Team.league_id == copa.id).delete()
    print(f"Deleted {teams_deleted} teams")
    
    # 6. Delete league
    db.delete(copa)
    print(f"Deleted league: {copa.name}")
    
    db.commit()
    print("\n✅ Copa Libertadores removed successfully!")
else:
    print("Copa Libertadores not found in database")

db.close()
