"""Quick test of live data functions"""
try:
    from backend.services.data_ingestion import (
        fetch_upcoming_fixtures, 
        fetch_recent_fixtures,
        fetch_teams_from_fixtures
    )
except ImportError:
    from services.data_ingestion import (
        fetch_upcoming_fixtures, 
        fetch_recent_fixtures,
        fetch_teams_from_fixtures
    )

print("Testing live data functions...")
league_id = 39  # Premier League

print("\n=== RECENT FIXTURES ===")
recent = fetch_recent_fixtures(league_id, count=10)
print(f"Got {len(recent)} recent fixtures")
if recent:
    for i, f in enumerate(recent[:3]):
        home = f['teams']['home']['name']
        away = f['teams']['away']['name']
        score = f"{f['goals']['home']}-{f['goals']['away']}"
        print(f"  {i+1}. {home} {score} {away}")

print("\n=== UPCOMING FIXTURES ===")
upcoming = fetch_upcoming_fixtures(league_id, count=10)
print(f"Got {len(upcoming)} upcoming fixtures")
if upcoming:
    for i, f in enumerate(upcoming[:3]):
        home = f['teams']['home']['name']
        away = f['teams']['away']['name']
        date = f['fixture']['date'][:10]
        print(f"  {i+1}. {home} vs {away} ({date})")

print("\n=== EXTRACTING TEAMS ===")
all_fixtures = recent + upcoming
teams = fetch_teams_from_fixtures(all_fixtures)
print(f"Found {len(teams)} unique teams")
for i, t in enumerate(teams[:5]):
    print(f"  {i+1}. {t['team']['name']}")
