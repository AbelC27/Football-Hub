"""Test live data availability from Football API"""
try:
    from backend.services.data_ingestion import fetch_teams, fetch_fixtures
    from backend.services.data_ingestion import headers, BASE_URL
except ImportError:
    from services.data_ingestion import fetch_teams, fetch_fixtures
    from services.data_ingestion import headers, BASE_URL

import requests
from datetime import datetime

print(f"Current date: {datetime.now().strftime('%Y-%m-%d')}\n")

# Test 1: Check 2025 season availability
print("=== TEST 1: CHECKING 2025 SEASON ===")
league_id = 39  # Premier League
for season in [2025, 2024]:
    teams = fetch_teams(league_id, season=season)
    print(f"Season {season}: {len(teams)} teams")
    if teams and len(teams) > 0:
        print(f"  ✓ Teams available for {season}")
        for i, t in enumerate(teams[:3]):
            print(f"    - {t['team']['name']}")
        break

# Test 2: Check live matches
print("\n=== TEST 2: LIVE MATCHES ===")
url = f"{BASE_URL}/fixtures"
params = {"live": "all"}
response = requests.get(url, headers=headers, params=params)
if response.status_code == 200:
    live_matches = response.json().get('response', [])
    print(f"Currently live matches: {len(live_matches)}")
    for match in live_matches[:5]:
        home = match['teams']['home']['name']
        away = match['teams']['away']['name']
        league = match['league']['name']
        print(f"  {home} vs {away} ({league})")
else:
    print(f"Error fetching live matches: {response.status_code}")

# Test 3: Today's fixtures
print("\n=== TEST 3: TODAY'S FIXTURES ===")
today = datetime.now().strftime('%Y-%m-%d')
params = {"date": today, "league": league_id}
response = requests.get(f"{BASE_URL}/fixtures", headers=headers, params=params)
if response.status_code == 200:
    today_matches = response.json().get('response', [])
    print(f"Matches today: {len(today_matches)}")
    for match in today_matches[:5]:
        home = match['teams']['home']['name']
        away = match['teams']['away']['name']
        time = match['fixture']['date']
        status = match['fixture']['status']['short']
        print(f"  {home} vs {away} - {time} ({status})")
else:
    print(f"Error: {response.status_code}")

# Test 4: Next 30 fixtures for Premier League
print("\n=== TEST 4: NEXT 30 FIXTURES (Premier League) ===")
params = {"league": league_id, "season": 2024, "next": 30}
response = requests.get(f"{BASE_URL}/fixtures", headers=headers, params=params)
if response.status_code == 200:
    upcoming = response.json().get('response', [])
    print(f"Upcoming fixtures: {len(upcoming)}")
    for match in upcoming[:5]:
        home = match['teams']['home']['name']
        away = match['teams']['away']['name']
        date = match['fixture']['date']
        print(f"  {home} vs {away} - {date}")
else:
    print(f"Error: {response.status_code}")

# Test 5: Last 50 fixtures (recent results)
print("\n=== TEST 5: LAST 50 FIXTURES (Recent Results) ===")
params = {"league": league_id, "season": 2024, "last": 50}
response = requests.get(f"{BASE_URL}/fixtures", headers=headers, params=params)
if response.status_code == 200:
    recent = response.json().get('response', [])
    print(f"Recent fixtures: {len(recent)}")
    for match in recent[:5]:
        home = match['teams']['home']['name']
        away = match['teams']['away']['name']
        score_home = match['goals']['home']
        score_away = match['goals']['away']
        status = match['fixture']['status']['short']
        print(f"  {home} {score_home}-{score_away} {away} ({status})")
else:
    print(f"Error: {response.status_code}")
