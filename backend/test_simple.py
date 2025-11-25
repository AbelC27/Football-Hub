"""Simpler test to check 2024/2025 season and live data"""
try:
    from backend.services.data_ingestion import fetch_teams
    from backend.services.data_ingestion import headers, BASE_URL
except ImportError:
    from services.data_ingestion import fetch_teams
    from services.data_ingestion import headers, BASE_URL

import requests

# Test season availability
print("=== SEASON AVAILABILITY ===")
league_id = 39
for season in [2025, 2024]:
    teams = fetch_teams(league_id, season=season)
    print(f"{season}: {len(teams)} teams")

# Test live matches endpoint
print("\n=== LIVE MATCHES ===")
url = f"{BASE_URL}/fixtures"
params = {"live": "all"}
response = requests.get(url, headers=headers, params=params)
data = response.json()
print(f"Status: {response.status_code}")
print(f"Live matches: {len(data.get('response', []))}")

# Test next fixtures
print("\n=== NEXT FIXTURES (2024 Season) ===")
params = {"league": league_id, "season": 2024, "next": 10}
response = requests.get(f"{BASE_URL}/fixtures", headers=headers, params=params)
data = response.json()
print(f"Status: {response.status_code}")
upcoming = data.get('response', [])
print(f"Upcoming: {len(upcoming)}")
if upcoming:
    for i, m in enumerate(upcoming[:3]):
        print(f"{i+1}. {m['teams']['home']['name']} vs {m['teams']['away']['name']}")

# Test last fixtures
print("\n=== LAST FIXTURES (2024 Season) ===")
params = {"league": league_id, "season": 2024, "last": 10}
response = requests.get(f"{BASE_URL}/fixtures", headers=headers, params=params)
data = response.json()
print(f"Status: {response.status_code}")
recent = data.get('response', [])
print(f"Recent: {len(recent)}")
if recent:
    for i, m in enumerate(recent[:3]):
        print(f"{i+1}. {m['teams']['home']['name']} vs {m['teams']['away']['name']}")
