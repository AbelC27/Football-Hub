"""
Football-Data.org API Integration
Free tier: 10 calls/minute, 12 competitions, current season data

API Documentation: https://docs.football-data.org
Register for free API key: https://www.football-data.org/client/register
"""
import requests
import os
from datetime import datetime, timedelta
from dotenv import load_dotenv

load_dotenv()

API_KEY = os.getenv("FOOTBALL_DATA_ORG_KEY")  # Add this to your .env file
BASE_URL = "https://api.football-data.org/v4"

headers = {
    'X-Auth-Token': API_KEY
}

def fetch_competitions():
    """Fetch available competitions"""
    url = f"{BASE_URL}/competitions"
    response = requests.get(url, headers=headers)
    if response.status_code == 200:
        return response.json().get('competitions', [])
    print(f"Failed to fetch competitions: {response.status_code}")
    return []

def fetch_competition_teams(competition_code='PL', season=None):
    """
    Fetch teams for a specific competition
    competition_code: 'PL' for Premier League, 'CL' for Champions League, etc.
    season: Year (e.g., 2024) - defaults to current season
    """
    url = f"{BASE_URL}/competitions/{competition_code}/teams"
    params = {}
    if season:
        params['season'] = season
    
    response = requests.get(url, headers=headers, params=params)
    if response.status_code == 200:
        return response.json().get('teams', [])
    print(f"Failed to fetch teams: {response.status_code}")
    return []

def fetch_competition_matches(competition_code='PL', status=None, matchday=None):
    """
    Fetch matches for a specific competition
    status: 'SCHEDULED', 'LIVE', 'FINISHED', or None for all
    matchday: Specific matchday number
    """
    url = f"{BASE_URL}/competitions/{competition_code}/matches"
    params = {}
    if status:
        params['status'] = status
    if matchday:
        params['matchday'] = matchday
    
    response = requests.get(url, headers=headers, params=params)
    if response.status_code == 200:
        return response.json().get('matches', [])
    print(f"Failed to fetch matches: {response.status_code} - {response.text}")
    return []

def fetch_all_matches(date_from=None, date_to=None, status=None):
    """
    Fetch all matches across all competitions
    date_from, date_to: YYYY-MM-DD format
    status: 'SCHEDULED',  'LIVE', 'FINISHED'
    """
    url = f"{BASE_URL}/matches"
    params = {}
    if date_from:
        params['dateFrom'] = date_from
    if date_to:
        params['dateTo'] = date_to
    if status:
        params['status'] = status
    
    response = requests.get(url, headers=headers, params=params)
    if response.status_code == 200:
        return response.json().get('matches', [])
    print(f"Failed to fetch matches: {response.status_code}")
    return []

def fetch_team_matches(team_id, status=None):
    """
    Fetch matches for a specific team
    team_id: Team ID
    status: 'SCHEDULED', 'LIVE', 'FINISHED'
    """
    url = f"{BASE_URL}/teams/{team_id}/matches"
    params = {}
    if status:
        params['status'] = status
    
    response = requests.get(url, headers=headers, params=params)
    if response.status_code == 200:
        return response.json().get('matches', [])
    print(f"Failed to fetch team matches: {response.status_code}")
    return []

def fetch_competition_standings(competition_code='PL'):
    """Fetch current standings for a competition"""
    url = f"{BASE_URL}/competitions/{competition_code}/standings"
    response = requests.get(url, headers=headers)
    if response.status_code == 200:
        return response.json().get('standings', [])
    print(f"Failed to fetch standings: {response.status_code}")
    return []

def fetch_competition_scorers(competition_code='PL'):
    """Fetch top scorers for a competition"""
    url = f"{BASE_URL}/competitions/{competition_code}/scorers"
    response = requests.get(url, headers=headers)
    if response.status_code == 200:
        return response.json().get('scorers', [])
    print(f"Failed to fetch scorers: {response.status_code}")
    return []

# Helper functions to match existing API structure

def parse_team_from_fd(team_data):
    """Convert Football-Data.org team format to our format"""
    return {
        'team': {
            'id': team_data['id'],
            'name': team_data['name'],
            'logo': team_data.get('crest', team_data.get('crestUrl', ''))
        },
        'venue': {
            'name': team_data.get('venue', 'Stadium')
        }
    }

def parse_match_from_fd(match_data):
    """Convert Football-Data.org match format to our format"""
    
    # Map statuses to our frontend format (Short codes)
    status_map = {
        'SCHEDULED': 'NS',
        'TIMED': 'NS',
        'IN_PLAY': 'LIVE',
        'PAUSED': 'HT',
        'FINISHED': 'FT',
        'SUSPENDED': 'SUSP',
        'POSTPONED': 'PST',
        'CANCELLED': 'CANC',
        'AWARDED': 'AWD'
    }
    
    api_status = match_data['status']
    short_status = status_map.get(api_status, api_status)
    
    return {
        'fixture': {
            'id': match_data['id'],
            'date': match_data['utcDate'],
            'status': {
                'short': short_status
            }
        },
        'teams': {
            'home': {
                'id': match_data['homeTeam']['id'],
                'name': match_data['homeTeam']['name'],
                'logo': match_data['homeTeam'].get('crest', '')
            },
            'away': {
                'id': match_data['awayTeam']['id'],
                'name': match_data['awayTeam']['name'],
                'logo': match_data['awayTeam'].get('crest', '')
            }
        },
        'goals': {
            'home': match_data['score']['fullTime']['home'],
            'away': match_data['score']['fullTime']['away']
        },
        'league': {
            'id': match_data['competition']['id'],
            'name': match_data['competition']['name']
        }
    }

def parse_standing_from_fd(standing_entry):
    """Convert Football-Data.org standing entry to our format"""
    return {
        'rank': standing_entry['position'],
        'team_id': standing_entry['team']['id'],
        'points': standing_entry['points'],
        'played': standing_entry['playedGames'],
        'won': standing_entry['won'],
        'drawn': standing_entry['draw'],
        'lost': standing_entry['lost'],
        'goals_for': standing_entry['goalsFor'],
        'goals_against': standing_entry['goalsAgainst'],
        'goal_difference': standing_entry['goalDifference'],
        'form': standing_entry.get('form')
    }

def parse_players_from_team(team_data):
    """Extract players from team data"""
    players = []
    squad = team_data.get('squad', [])
    
    for player in squad:
        players.append({
            'id': player['id'],
            'name': player['name'],
            'position': player['position'],
            'nationality': player['nationality'],
            'date_of_birth': player.get('dateOfBirth')
        })
    
    return players
