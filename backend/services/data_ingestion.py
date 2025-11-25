import requests
import os
from datetime import datetime
from dotenv import load_dotenv

load_dotenv()

API_KEY = os.getenv("API_FOOTBALL_KEY")
BASE_URL = "https://v3.football.api-sports.io"

headers = {
    'x-apisports-key': API_KEY
}

def fetch_leagues():
    url = f"{BASE_URL}/leagues"
    # Fetching ONLY Premier League (39) to save requests
    target_ids = [39]
    response = requests.get(url, headers=headers)
    if response.status_code == 200:
        data = response.json().get('response', [])
        if not data:
            print(f"No leagues found. Response: {response.json()}")
        return [l for l in data if l['league']['id'] in target_ids]
    print(f"Failed to fetch leagues: {response.status_code} {response.text}")
    return []

def fetch_teams(league_id, season=2023):
    url = f"{BASE_URL}/teams"
    querystring = {"league": str(league_id), "season": str(season)}
    response = requests.get(url, headers=headers, params=querystring)
    if response.status_code == 200:
        return response.json()['response']
    return []

def fetch_fixtures(league_id, season=2023):
    url = f"{BASE_URL}/fixtures"
    querystring = {"league": str(league_id), "season": str(season)}
    response = requests.get(url, headers=headers, params=querystring)
    if response.status_code == 200:
        return response.json().get('response', [])
    print(f"Failed to fetch fixtures: {response.status_code}")
    return []

def fetch_fixture_stats(fixture_id):
    url = f"{BASE_URL}/fixtures/statistics"
    querystring = {"fixture": str(fixture_id)}
    response = requests.get(url, headers=headers, params=querystring)
    if response.status_code == 200:
        return response.json()['response']
    return []

def fetch_match_events(match_id):
    """Fetch events for a specific match"""
    url = f"{BASE_URL}/fixtures/events"
    params = {'fixture': match_id}
    response = requests.get(url, headers=headers, params=params)
    if response.status_code == 200:
        return response.json().get('response', [])
    print(f"Failed to fetch events for match {match_id}: {response.status_code}")
    return []

def fetch_match_statistics(match_id):
    """Fetch statistics for a specific match"""
    url = f"{BASE_URL}/fixtures/statistics"
    params = {'fixture': match_id}
    response = requests.get(url, headers=headers, params=params)
    if response.status_code == 200:
        return response.json().get('response', [])
    print(f"Failed to fetch statistics for match {match_id}: {response.status_code}")
    return []

def fetch_live_fixtures():
    """Fetch all currently live matches"""
    url = f"{BASE_URL}/fixtures"
    params = {'live': 'all'}
    response = requests.get(url, headers=headers, params=params)
    if response.status_code == 200:
        return response.json().get('response', [])
    print(f"Failed to fetch live fixtures: {response.status_code}")
    return []

def fetch_fixtures_by_date(date_str):
    """Fetch fixtures for a specific date (YYYY-MM-DD format)"""
    url = f"{BASE_URL}/fixtures"
    params = {'date': date_str}
    response = requests.get(url, headers=headers, params=params)
    if response.status_code == 200:
        return response.json().get('response', [])
    print(f"Failed to fetch fixtures for {date_str}: {response.status_code}")
    return []

def fetch_fixtures_date_range(start_date, end_date, league_id=None):
    """
    Fetch fixtures within a date range
    start_date, end_date: datetime objects
    league_id: optional filter by league
    """
    from datetime import timedelta
    all_fixtures = []
    
    current_date = start_date
    while current_date <= end_date:
        date_str = current_date.strftime('%Y-%m-%d')
        print(f"  Fetching fixtures for {date_str}...")
        fixtures = fetch_fixtures_by_date(date_str)
        
        # Filter by league if specified
        if league_id:
            fixtures = [f for f in fixtures if f['league']['id'] == league_id]
        
        all_fixtures.extend(fixtures)
        print(f"    Found {len(fixtures)} fixtures")
        
        current_date += timedelta(days=1)
    
    return all_fixtures

def fetch_upcoming_fixtures(league_id, count=50):
    """Fetch upcoming fixtures for a league using date range"""
    from datetime import datetime, timedelta
    today = datetime.now()
    # Fetch next 7 days
    end_date = today + timedelta(days=7)
    return fetch_fixtures_date_range(today, end_date, league_id)

def fetch_recent_fixtures(league_id, count=50):
    """Fetch recent/completed fixtures for a league using date range"""
    from datetime import datetime, timedelta
    today = datetime.now()
    # Fetch last 7 days
    start_date = today - timedelta(days=7)
    return fetch_fixtures_date_range(start_date, today, league_id)

def fetch_teams_from_fixtures(fixtures_data):
    """Extract unique teams from fixtures data"""
    teams_dict = {}
    for fixture in fixtures_data:
        for side in ['home', 'away']:
            team_data = fixture['teams'][side]
            team_id = team_data['id']
            if team_id not in teams_dict:
                teams_dict[team_id] = {
                    'team': {
                        'id': team_id,
                        'name': team_data['name'],
                        'logo': team_data['logo']
                    },
                    'venue': {
                        'name': 'Stadium'  # Placeholder, would need separate API call
                    }
                }
    return list(teams_dict.values())


