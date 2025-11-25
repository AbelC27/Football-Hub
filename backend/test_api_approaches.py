"""Test different API approaches"""
try:
    from backend.services.data_ingestion import headers, BASE_URL
except ImportError:
    from services.data_ingestion import headers, BASE_URL

import requests
from datetime import datetime, timedelta

# Try fetching fixtures by date
today = datetime.now()
date_str = today.strftime('%Y-%m-%d')
yesterday = (today - timedelta(days=1)).strftime('%Y-%m-%d')
tomorrow = (today + timedelta(days=1)).strftime('%Y-%m-%d')

print(f"Today: {date_str}\n")

# Test 1: Today's fixtures
print("=== TODAY'S FIXTURES ===")
url = f"{BASE_URL}/fixtures"
params = {"date": date_str}
response = requests.get(url, headers=headers, params=params)
print(f"Status: {response.status_code}")
if response.status_code == 200:
    data = response.json()
    fixtures = data.get('response', [])
    print(f"Fixtures today: {len(fixtures)}")
    for i, f in enumerate(fixtures[:5]):
        league = f['league']['name']
        home = f['teams']['home']['name']
        away = f['teams']['away']['name']
        print(f"  {i+1}. {home} vs {away} ({league})")

# Test 2: Specific league + season + last N
print("\n=== PREMIER LEAGUE LAST 20 MATCHES ===")
params = {"league": "39", "season": "2024", "last": "20"}
response = requests.get(url, headers=headers, params=params)
print(f"Status: {response.status_code}")
data = response.json()
print(f"Response keys: {data.keys()}")
if 'errors' in data and data['errors']:
    print(f"ERRORS: {data['errors']}")
if 'response' in data:
    fixtures = data.get('response', [])
    print(f"Fixtures: {len(fixtures)}")
    for i, f in enumerate(fixtures[:3]):
        home = f['teams']['home']['name']
        away = f['teams']['away']['name']
        score_h = f['goals']['home']
        score_a = f['goals']['away']
        print(f"  {i+1}. {home} {score_h}-{score_a} {away}")

# Test 3: Check account status
print("\n=== API STATUS ===")
url_status = f"{BASE_URL}/status"
response = requests.get(url_status, headers=headers)
if response.status_code == 200:
    status_data = response.json()
    print(f"Response: {status_data}")
