from backend.database import SessionLocal, engine, Base
from backend.models import League, Team, Match
from sqlalchemy.orm import Session
import datetime
import random

# Create tables
Base.metadata.create_all(bind=engine)

def seed_mock_data(db: Session):
    print("Seeding Mock Data...")
    
    # 1. Leagues
    leagues = [
        {"id": 39, "name": "Premier League", "country": "England", "logo": "https://media.api-sports.io/football/leagues/39.png"},
        {"id": 140, "name": "La Liga", "country": "Spain", "logo": "https://media.api-sports.io/football/leagues/140.png"},
        {"id": 78, "name": "Bundesliga", "country": "Germany", "logo": "https://media.api-sports.io/football/leagues/78.png"},
        {"id": 135, "name": "Serie A", "country": "Italy", "logo": "https://media.api-sports.io/football/leagues/135.png"},
        {"id": 61, "name": "Ligue 1", "country": "France", "logo": "https://media.api-sports.io/football/leagues/61.png"},
    ]
    
    created_leagues = []
    for l in leagues:
        existing = db.query(League).filter(League.id == l['id']).first()
        if not existing:
            new_league = League(id=l['id'], name=l['name'], country=l['country'], logo_url=l['logo'])
            db.add(new_league)
            created_leagues.append(new_league)
        else:
            created_leagues.append(existing)
    db.commit()
    
    # 2. Teams (10 teams per league for demo)
    created_teams = []
    for league in created_leagues:
        for i in range(10):
            team_id = league.id * 100 + i
            existing = db.query(Team).filter(Team.id == team_id).first()
            if not existing:
                new_team = Team(
                    id=team_id,
                    name=f"{league.name} Team {i+1}",
                    logo_url="https://media.api-sports.io/football/teams/33.png", # Placeholder
                    stadium="Generic Stadium",
                    league_id=league.id
                )
                db.add(new_team)
                created_teams.append(new_team)
            else:
                created_teams.append(existing)
    db.commit()
    
    # 3. Matches (Fixtures)
    # Generate matches between teams in same league
    # Some FT (past), some LIVE, some NS (future)
    
    statuses = ['FT', 'FT', 'FT', 'LIVE', 'NS', 'NS']
    
    for league in created_leagues:
        league_teams = [t for t in created_teams if t.league_id == league.id]
        # Round robin simple
        for i in range(len(league_teams)):
            for j in range(i+1, len(league_teams)):
                home = league_teams[i]
                away = league_teams[j]
                
                match_id = home.id * 10000 + away.id
                existing = db.query(Match).filter(Match.id == match_id).first()
                
                if not existing:
                    status = random.choice(statuses)
                    start_time = datetime.datetime.now()
                    
                    home_score = None
                    away_score = None
                    
                    if status == 'FT':
                        start_time = datetime.datetime.now() - datetime.timedelta(days=random.randint(1, 30))
                        home_score = random.randint(0, 5)
                        away_score = random.randint(0, 5)
                    elif status == 'LIVE':
                        start_time = datetime.datetime.now() - datetime.timedelta(minutes=random.randint(10, 80))
                        home_score = random.randint(0, 3)
                        away_score = random.randint(0, 3)
                    else: # NS
                        start_time = datetime.datetime.now() + datetime.timedelta(days=random.randint(1, 14))
                    
                    new_match = Match(
                        id=match_id,
                        home_team_id=home.id,
                        away_team_id=away.id,
                        start_time=start_time,
                        status=status,
                        home_score=home_score,
                        away_score=away_score
                    )
                    db.add(new_match)
    db.commit()
    print("Mock Data Seeded.")

if __name__ == "__main__":
    db = SessionLocal()
    try:
        seed_mock_data(db)
    finally:
        db.close()
