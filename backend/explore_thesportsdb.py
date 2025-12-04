"""
Explore TheSportsDB API for UEFA competitions
"""
import requests
import json

API_KEY = "3"  # Free test key
BASE_URL = f"https://www.thesportsdb.com/api/v1/json/{API_KEY}"

print("Testing TheSportsDB API for UEFA competitions...")
print("=" * 60)

# Try to search for UEFA competitions
print("\n1. Searching for 'Champions League'...")
try:
    url = f"{BASE_URL}/search_all_leagues.php?s=Soccer"
    response = requests.get(url)
    if response.status_code == 200:
        data = response.json()
        if data and data.get('countries'):
            # Filter for UEFA competitions
            uefa_leagues = [c for c in data['countries'] if 'UEFA' in c.get('strLeague', '') or 'Champions' in c.get('strLeague', '') or 'Europa' in c.get('strLeague', '')]
            print(f"Found {len(uefa_leagues)} UEFA-related leagues")
            for league in uefa_leagues[:5]:
                print(f"  - {league.get('strLeague')} (ID: {league.get('idLeague')})")
except Exception as e:
    print(f"Error: {e}")

# Try alternative endpoint
print("\n2. Looking up specific league by name...")
try:
    leagues_to_check = ['UEFA Champions League', 'UEFA Europa League', 'UEFA Conference League']
    for league_name in leagues_to_check:
        url = f"{BASE_URL}/search_all_leagues.php?l={league_name}"
        response = requests.get(url)
        if response.status_code == 200:
            data = response.json()
            if data and data.get('leagues'):
                print(f"\n{league_name}:")
                for league in data['leagues']:
                    print(f"  ID: {league.get('idLeague')}")
                    print(f"  Sport: {league.get('strSport')}")
                    print(f"  Country: {league.get('strCountry')}")
except Exception as e:
    print(f"Error: {e}")

# Check if we can get events (matches) for a league
print("\n3. Checking available API endpoints...")
print("  - /eventspastleague.php?id=<league_id> - Past events")
print("  - /eventsnextleague.php?id=<league_id> - Upcoming events")
print("  - /eventsseason.php?id=<league_id>&s=<season> - Events for a season")
print("  - /lookuptable.php?l=<league_id>&s=<season> - League table/standings")

print("\n" + "=" * 60)
print("TheSportsDB uses a different data model than Football-Data.org")
print("They organize by 'events' (matches) rather than fixtures")
print("We would need to:")
print("1. Find the correct league IDs for UEFA competitions")
print("2. Fetch events for current season")
print("3. Map teams and create our own standings logic")
