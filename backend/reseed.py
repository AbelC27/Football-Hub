"""
This script clears the database and reseeds it with proper team and fixture data.
It ensures that only fixtures involving teams we have in the database are added.
"""
try:
    from backend.services.data_ingestion import fetch_leagues, fetch_teams, fetch_fixtures
    from backend.database import SessionLocal, engine, Base
    from backend.models import League, Team, Match
except ImportError:
    from services.data_ingestion import fetch_leagues, fetch_teams, fetch_fixtures
    from database import SessionLocal, engine, Base
    from models import League, Team, Match
    
from sqlalchemy.orm import Session
import datetime

# Drop all tables and recreate them
print("Dropping all tables...")
Base.metadata.drop_all(bind=engine)
print("Creating all tables...")
Base.metadata.create_all(bind=engine)

def seed_leagues(db: Session):
    print("Seeding Leagues...")
    leagues_data = fetch_leagues()
    for l_data in leagues_data:
        league = l_data['league']
        country = l_data['country']
        
        new_league = League(
            id=league['id'],
            name=league['name'],
            country=country['name'],
            logo_url=league['logo']
        )
        db.add(new_league)
    db.commit()
    print(f"Seeded {len(leagues_data)} leagues.")

def seed_teams(db: Session):
    print("Seeding Teams...")
    leagues = db.query(League).all()
    team_ids = set()
    
    for league in leagues:
        print(f"Fetching teams for {league.name}...")
        teams_data = fetch_teams(league.id, season=2023)  # Changed to 2023
        count = 0
        for t_data in teams_data:
            if count >= 10:  # Increased to 10 teams per league for more variety
                break
            count += 1
            team = t_data['team']
            venue = t_data['venue']
            
            new_team = Team(
                id=team['id'],
                name=team['name'],
                logo_url=team['logo'],
                stadium=venue['name'],
                league_id=league.id
            )
            db.add(new_team)
            team_ids.add(team['id'])
        db.commit()
    
    print(f"Seeded {len(team_ids)} teams total.")
    return team_ids

def seed_fixtures(db: Session, valid_team_ids: set):
    print("Seeding Fixtures...")
    leagues = db.query(League).all()
    total_fixtures = 0
    
    # Try both 2023 and 2024 seasons (2023 first as it has more data)
    seasons = [2023, 2024]
    
    for season in seasons:
        print(f"\nTrying season {season}...")
        for league in leagues:
            print(f"Fetching fixtures for {league.name} (season {season})...")
            fixtures_data = fetch_fixtures(league.id, season=season)
            print(f"  Received {len(fixtures_data)} total fixtures from API")
            
            matches_added_for_league = 0
            for f_data in fixtures_data:
                fixture = f_data['fixture']
                goals = f_data['goals']
                teams = f_data['teams']
                
                home_team_id = teams['home']['id']
                away_team_id = teams['away']['id']
                
                # ONLY add fixture if BOTH teams are in our database
                if home_team_id in valid_team_ids and away_team_id in valid_team_ids:
                    # Check if fixture already exists
                    existing = db.query(Match).filter(Match.id == fixture['id']).first()
                    if not existing:
                        # Parse date
                        dt_str = fixture['date']
                        dt_obj = datetime.datetime.fromisoformat(dt_str)
                        
                        new_match = Match(
                            id=fixture['id'],
                            home_team_id=home_team_id,
                            away_team_id=away_team_id,
                            start_time=dt_obj,
                            status=fixture['status']['short'],
                            home_score=goals['home'],
                            away_score=goals['away']
                        )
                        db.add(new_match)
                        total_fixtures += 1
                        matches_added_for_league += 1
            
            print(f"  Added {matches_added_for_league} fixtures for {league.name} (season {season})")
            db.commit()
        
        # If we got fixtures, don't try the next season
        if total_fixtures > 0:
            break
    
    print(f"\nSeeded {total_fixtures} fixtures total.")
    if total_fixtures == 0:
        print("⚠️ WARNING: No fixtures were added! Check if the team IDs match fixture team IDs.")

if __name__ == "__main__":
    db = SessionLocal()
    try:
        seed_leagues(db)
        valid_team_ids = seed_teams(db)
        seed_fixtures(db, valid_team_ids)
        print("\n✅ Database reseeded successfully!")
    except Exception as e:
        print(f"\n❌ Error during reseeding: {e}")
        import traceback
        traceback.print_exc()
    finally:
        db.close()
