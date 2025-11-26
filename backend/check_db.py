from database import SessionLocal
from models import League, Team, Match, Standing, Player

db = SessionLocal()
leagues = db.query(League).all()
print('Leagues:')
for l in leagues:
    team_count = db.query(Team).filter(Team.league_id == l.id).count()
    standing_count = db.query(Standing).filter(Standing.league_id == l.id).count()
    print(f'  - {l.name} (ID: {l.id}) - Teams: {team_count}, Standings: {standing_count}')

total_leagues = len(leagues)
total_teams = db.query(Team).count()
total_players = db.query(Player).count()
total_matches = db.query(Match).count()

print(f'\nTotal Stats:')
print(f'  Leagues: {total_leagues}')
print(f'  Teams: {total_teams}')
print(f'  Players: {total_players}')
print(f'  Matches: {total_matches}')

db.close()
