"""Check if API is working and we can fetch teams"""
try:
    from backend.services.data_ingestion import fetch_leagues, fetch_teams
except ImportError:
    from services.data_ingestion import fetch_leagues, fetch_teams

# Test fetching leagues
print("=== FETCHING LEAGUES ===")
leagues = fetch_leagues()
print(f"Got {len(leagues)} leagues")
for l in leagues:
    print(f"  League {l['league']['id']}: {l['league']['name']}")

# Test fetching teams for different seasons
if leagues:
    league_id = leagues[0]['league']['id']
    for season in [2024, 2023, 2022]:
        print(f"\n=== FETCHING TEAMS FOR LEAGUE {league_id} (Season {season}) ===")
        teams = fetch_teams(league_id, season=season)
        print(f"Got{len(teams)} teams")
        if teams:
            for i, t in enumerate(teams[:10]):
                team = t['team']
                print(f"  {i+1}. Team {team['id']}: {team['name']}")
            break  # Stop if we found teams
