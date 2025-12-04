"""
Test TheSportsDB API directly to see what we get
"""
import requests

API_KEY = "3"
BASE_URL = f"https://www.thesportsdb.com/api/v1/json/{API_KEY}"

# Test 1: Get all soccer leagues
print("Test 1: Getting all soccer leagues...")
url = f"{BASE_URL}/all_leagues.php"
response = requests.get(url, timeout=10)
print(f"Status: {response.status_code}")

if response.status_code == 200:
    data = response.json()
    if data and data.get('leagues'):
        uefa_leagues = [l for l in data['leagues'] if 'Champions' in l.get('strLeague', '') or 'Europa' in l.get('strLeague', '')]
        print(f"\nFound {len(uefa_leagues)} UEFA leagues:")
        for league in uefa_leagues[:5]:
            print(f"  - {league.get('strLeague')} (ID: {league.get('idLeague')})")

# Test 2: Try to get Champions League events directly
print("\n\nTest 2: Getting Champions League events...")
# Known ID for Champions League
league_ids_to_try = [4480, 4481]

for league_id in league_ids_to_try:
    print(f"\nTrying league ID: {league_id}")
    url = f"{BASE_URL}/eventspastleague.php?id={league_id}"
    response = requests.get(url, timeout=10)
    
    if response.status_code == 200:
        data = response.json()
        if data and data.get('events'):
            print(f"  ✓ Found {len(data['events'])} past events")
            if data['events']:
                sample = data['events'][0]
                print(f"  Sample: {sample.get('strHomeTeam')} vs {sample.get('strAwayTeam')}")
        else:
            print(f"  No events found")
    else:
        print(f"  API error: {response.status_code}")
