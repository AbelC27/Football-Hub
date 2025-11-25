from database import SessionLocal
from models import Match, Player, Team

db = SessionLocal()

# Get a match
match = db.query(Match).first()
if match:
    print(f"Match ID: {match.id}")
    print(f"Home Team ID: {match.home_team_id}")
    
    # Check players for home team
    players = db.query(Player).filter(Player.team_id == match.home_team_id).all()
    print(f"Players found for team {match.home_team_id}: {len(players)}")
    
    if players:
        print(f"First player: {players[0].name} (ID: {players[0].id}, TeamID: {players[0].team_id})")
    else:
        # Check if any players exist at all
        count = db.query(Player).count()
        print(f"Total players in DB: {count}")
        
        # Check if the team exists
        team = db.query(Team).filter(Team.id == match.home_team_id).first()
        if team:
            print(f"Team exists: {team.name}")
        else:
            print("Team does not exist!")

db.close()
