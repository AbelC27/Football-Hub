"""
Live Data Seeder - Fetches current/upcoming fixtures and recent results
This replaces historical season data with current, live data
"""
try:
    from backend.services.data_ingestion import (
        fetch_leagues, 
        fetch_upcoming_fixtures, 
        fetch_recent_fixtures,
        fetch_live_fixtures,
        fetch_teams_from_fixtures
    )
    from backend.database import SessionLocal, engine, Base
    from backend.models import League, Team, Match
except ImportError:
    from services.data_ingestion import (
        fetch_leagues, 
        fetch_upcoming_fixtures, 
        fetch_recent_fixtures,
        fetch_live_fixtures,
        fetch_teams_from_fixtures
    )
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
    print("\n=== SEEDING LEAGUES ===")
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
    print(f"✓ Seeded {len(leagues_data)} leagues")
    return leagues_data

def seed_teams_and_fixtures_live(db: Session, leagues_data: list):
    """
    Seed teams and fixtures using LIVE DATA:
    - Fetch recent fixtures (last 7 days)
    - Fetch upcoming fixtures (next 7 days)
    - Extract teams from these fixtures
    - Add both teams and fixtures to database
    """
    print("\n=== SEEDING TEAMS & FIXTURES (LIVE DATA) ===")
    
    all_fixtures = []
    team_ids = set()
    
    for l_data in leagues_data:
        league_id = l_data['league']['id']
        league_name = l_data['league']['name']
        
        print(f"\n{league_name}:")
        
        # Fetch recent fixtures (last 7 days)
        print("  Fetching recent fixtures (last 7 days)...")
        recent = fetch_recent_fixtures(league_id, count=10)  # count is ignored, uses date range
        print(f"  ✓ Got {len(recent)} recent fixtures")
        
        # Fetch upcoming fixtures (next 7 days)
        print("  Fetching upcoming fixtures (next 7 days)...")
        upcoming = fetch_upcoming_fixtures(league_id, count=10)  # count is ignored, uses date range
        print(f"  ✓ Got {len(upcoming)} upcoming fixtures")
        
        # Combine all fixtures
        all_fixtures.extend(recent)
        all_fixtures.extend(upcoming)
    
    print(f"\n✓ Total fixtures collected: {len(all_fixtures)}")
    
    # Extract unique teams from fixtures
    print("\nExtracting teams from fixtures...")
    teams_data = fetch_teams_from_fixtures(all_fixtures)
    print(f"✓ Found {len(teams_data)} unique teams")
    
    # Add teams to database
    print("\nAdding teams to database...")
    for t_data in teams_data:
        team = t_data['team']
        venue = t_data['venue']
        
        # Get league_id from first fixture involving this team
        league_id = 39  # Default to Premier League
        for fixture in all_fixtures:
            if fixture['teams']['home']['id'] == team['id'] or \
               fixture['teams']['away']['id'] == team['id']:
                league_id = fixture['league']['id']
                break
        
        new_team = Team(
            id=team['id'],
            name=team['name'],
            logo_url=team['logo'],
            stadium=venue.get('name', 'Stadium'),
            league_id=league_id
        )
        db.add(new_team)
        team_ids.add(team['id'])
    
    db.commit()
    print(f"✓ Added {len(team_ids)} teams to database")
    
    # Add fixtures to database
    print("\nAdding fixtures to database...")
    fixtures_added = 0
    for f_data in all_fixtures:
        fixture = f_data['fixture']
        goals = f_data['goals']
        teams = f_data['teams']
        
        home_team_id = teams['home']['id']
        away_team_id = teams['away']['id']
        
        # Only add if both teams are in our database
        if home_team_id in team_ids and away_team_id in team_ids:
            # Parse date
            dt_str = fixture['date']
            dt_obj = datetime.datetime.fromisoformat(dt_str)
            
            # Check if already exists
            existing = db.query(Match).filter(Match.id == fixture['id']).first()
            if not existing:
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
                fixtures_added += 1
    
    db.commit()
    print(f"✓ Added {fixtures_added} fixtures to database")
    
    return len(team_ids), fixtures_added

if __name__ == "__main__":
    db = SessionLocal()
    try:
        print("=" * 60)
        print("LIVE DATA SEEDER - Fetching Current Matches")
        print("=" * 60)
        
        leagues_data = seed_leagues(db)
        teams_count, fixtures_count = seed_teams_and_fixtures_live(db, leagues_data)
        
        print("\n" + "=" * 60)
        print("✅ DATABASE SEEDED SUCCESSFULLY WITH LIVE DATA!")
        print("=" * 60)
        print(f"Teams: {teams_count}")
        print(f"Fixtures: {fixtures_count}")
        print("=" * 60)
        
    except Exception as e:
        print(f"\n❌ Error during reseeding: {e}")
        import traceback
        traceback.print_exc()
    finally:
        db.close()
