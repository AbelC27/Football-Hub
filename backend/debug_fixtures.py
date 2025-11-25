"""Debug script to see what team IDs we have vs what's in fixtures"""
try:
    from backend.services.data_ingestion import fetch_teams, fetch_fixtures
    from backend.database import SessionLocal
    from backend.models import League, Team
except ImportError:
    from services.data_ingestion import fetch_teams, fetch_fixtures
    from database import SessionLocal
    from models import League, Team

db = SessionLocal()

# Get teams in our database
print("=== TEAMS IN DATABASE ===")
teams = db.query(Team).all()
team_ids = {t.id for t in teams}
print(f"Team IDs: {sorted(team_ids)}")
for team in teams[:10]:  # Show first 10 teams
    print(f"  {team.id}: {team.name}")

# Get leagues
leagues = db.query(League).all()

# Check what team IDs are in fixtures
print("\n=== CHECKING FIXTURES (2024 Season) ===")
for league in leagues:
    fixtures_data = fetch_fixtures(league.id, season=2024)
    print(f"\n{league.name}: {len(fixtures_data)} total fixtures")
    
    fixture_team_ids = set()
    sample_fixtures = []
    for f in fixtures_data[:5]:  # Show first 5 fixtures
        home_id = f['teams']['home']['id']
        away_id = f['teams']['away']['id']
        home_name = f['teams']['home']['name']
        away_name = f['teams']['away']['name']
        fixture_team_ids.add(home_id)
        fixture_team_ids.add(away_id)
        sample_fixtures.append(f"{home_name} ({home_id}) vs {away_name} ({away_id})")
    
    print("Sample fixtures:")
    for sf in sample_fixtures:
        print(f"  {sf}")
    
    # Check overlap
    print(f"\nFixture has {len(fixture_team_ids)} unique teams")
    overlap = team_ids.intersection(fixture_team_ids)
    print(f"Overlap with our teams: {len(overlap)} teams")
    if overlap:
        print(f"  Overlapping IDs: {sorted(overlap)}")

# Try 2023 season too
print("\n=== CHECKING FIXTURES (2023 Season) ===")
for league in leagues:
    fixtures_data = fetch_fixtures(league.id, season=2023)
    print(f"\n{league.name}: {len(fixtures_data)} total fixtures")
    
    fixture_team_ids = set()
    for f in fixtures_data:
        home_id = f['teams']['home']['id']
        away_id = f['teams']['away']['id']
        fixture_team_ids.add(home_id)
        fixture_team_ids.add(away_id)
    
    print(f"Fixture has {len(fixture_team_ids)} unique teams")
    overlap = team_ids.intersection(fixture_team_ids)
    print(f"Overlap with our teams: {len(overlap)} teams")
    
    # Count how many fixtures would match
    valid_count = 0
    for f in fixtures_data:
        home_id = f['teams']['home']['id']
        away_id = f['teams']['away']['id']
        if home_id in team_ids and away_id in team_ids:
            valid_count += 1
    print(f"Valid fixtures (both teams in DB): {valid_count}")

db.close()
