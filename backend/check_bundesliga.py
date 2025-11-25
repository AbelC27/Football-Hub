from database import SessionLocal
from models import League, Team

db = SessionLocal()

# Check Bundesliga
bl = db.query(League).filter(League.name.like('%Bundesliga%')).first()
if bl:
    teams = db.query(Team).filter(Team.league_id == bl.id).all()
    print(f'Bundesliga ID: {bl.id}')
    print(f'Teams count: {len(teams)}')
    print('\nTeams:')
    for t in teams:
        print(f'{t.id}: {t.name}')
else:
    print("Bundesliga not found")

db.close()
