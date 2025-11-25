from backend.services.data_ingestion import fetch_leagues, fetch_teams, fetch_fixtures
from backend.database import SessionLocal, engine, Base
from backend.models import League, Team, Match
from sqlalchemy.orm import Session
import datetime

# Create tables
Base.metadata.create_all(bind=engine)

def seed_leagues(db: Session):
    print("Seeding Leagues...")
    leagues_data = fetch_leagues()
    for l_data in leagues_data:
        league = l_data['league']
        country = l_data['country']
        
        existing = db.query(League).filter(League.id == league['id']).first()
        if not existing:
            new_league = League(
                id=league['id'],
                name=league['name'],
                country=country['name'],
                logo_url=league['logo']
            )
            db.add(new_league)
    db.commit()
    print("Leagues seeded.")

def seed_teams(db: Session):
    print("Seeding Teams...")
    leagues = db.query(League).all()
    for league in leagues:
        print(f"Fetching teams for {league.name}...")
        teams_data = fetch_teams(league.id, season=2024) # Updated season
        count = 0
        for t_data in teams_data:
            if count >= 5: break # LIMIT to 5 teams per league
            count += 1
            team = t_data['team']
            venue = t_data['venue']
            
            existing = db.query(Team).filter(Team.id == team['id']).first()
            if not existing:
                new_team = Team(
                    id=team['id'],
                    name=team['name'],
                    logo_url=team['logo'],
                    stadium=venue['name'],
                    league_id=league.id
                )
                db.add(new_team)
        db.commit()
    print("Teams seeded.")

def seed_fixtures(db: Session):
    print("Seeding Fixtures (2024)...")
    leagues = db.query(League).all()
    for league in leagues:
        print(f"Fetching fixtures for {league.name}...")
        fixtures_data = fetch_fixtures(league.id, season=2024)
        for f_data in fixtures_data:
            fixture = f_data['fixture']
            goals = f_data['goals']
            teams = f_data['teams']
            
            existing = db.query(Match).filter(Match.id == fixture['id']).first()
            if not existing:
                # Parse date
                # "2023-08-11T19:00:00+00:00"
                dt_str = fixture['date']
                dt_obj = datetime.datetime.fromisoformat(dt_str)
                
                new_match = Match(
                    id=fixture['id'],
                    home_team_id=teams['home']['id'],
                    away_team_id=teams['away']['id'],
                    start_time=dt_obj,
                    status=fixture['status']['short'],
                    home_score=goals['home'],
                    away_score=goals['away']
                )
                db.add(new_match)
        db.commit()
    print("Fixtures seeded.")

if __name__ == "__main__":
    db = SessionLocal()
    try:
        seed_leagues(db)
        seed_teams(db)
        seed_fixtures(db)
    finally:
        db.close()
