"""
Football-Data.org API Integration
Free tier: 10 calls/minute, 12 competitions, current season data

API Documentation: https://docs.football-data.org
Register for free API key: https://www.football-data.org/client/register
"""
import logging
import os
import threading
import time
from collections import deque
from datetime import datetime, timedelta

import requests
from dotenv import load_dotenv

load_dotenv()

API_KEY = os.getenv("FOOTBALL_DATA_ORG_KEY")  # Add this to your .env file
BASE_URL = "https://api.football-data.org/v4"

headers = {
    'X-Auth-Token': API_KEY
}

logger = logging.getLogger(__name__)

# --- Rate limiting --------------------------------------------------------
# football-data.org free tier allows 10 requests per minute. We enforce a
# sliding window client-side so background jobs and seed scripts never blow
# through the quota and trigger 429 storms. The window size is configurable
# via env vars to make it easy to dial down further on shared keys.

_RATE_LIMIT_MAX_CALLS = int(os.getenv("FOOTBALL_DATA_RATE_LIMIT_CALLS", "9"))
_RATE_LIMIT_WINDOW_SECONDS = float(os.getenv("FOOTBALL_DATA_RATE_LIMIT_WINDOW", "60"))
_RATE_LIMIT_MAX_RETRIES = int(os.getenv("FOOTBALL_DATA_MAX_RETRIES", "3"))

_rate_lock = threading.Lock()
_recent_call_timestamps: deque = deque()


def _wait_for_slot():
    """Block until we have a free slot in the sliding rate-limit window."""
    while True:
        with _rate_lock:
            now = time.monotonic()
            # Drop timestamps that fall outside the window.
            while _recent_call_timestamps and now - _recent_call_timestamps[0] >= _RATE_LIMIT_WINDOW_SECONDS:
                _recent_call_timestamps.popleft()

            if len(_recent_call_timestamps) < _RATE_LIMIT_MAX_CALLS:
                _recent_call_timestamps.append(now)
                return

            # Otherwise wait until the oldest call leaves the window.
            sleep_for = _RATE_LIMIT_WINDOW_SECONDS - (now - _recent_call_timestamps[0])
        # Sleep outside the lock so other threads can release slots.
        time.sleep(max(sleep_for, 0.05))


def _request_get(url, params=None, timeout=15):
    """
    Throttled GET wrapper for football-data.org.

    Enforces a client-side rate limit and retries on 429 using the API's
    `Retry-After` hint (or the embedded "Wait N seconds" message) so a single
    burst doesn't cascade into a flood of failed calls.
    """
    attempt = 0
    while True:
        _wait_for_slot()
        try:
            response = requests.get(url, headers=headers, params=params, timeout=timeout)
        except requests.RequestException as exc:
            if attempt >= _RATE_LIMIT_MAX_RETRIES:
                logger.warning("Request to %s failed after %s retries: %s", url, attempt, exc)
                raise
            attempt += 1
            time.sleep(min(2 ** attempt, 10))
            continue

        if response.status_code != 429:
            return response

        if attempt >= _RATE_LIMIT_MAX_RETRIES:
            return response

        # Honour the API's wait hint; fall back to the window length.
        wait_seconds = _RATE_LIMIT_WINDOW_SECONDS
        retry_after = response.headers.get("Retry-After")
        if retry_after:
            try:
                wait_seconds = float(retry_after)
            except ValueError:
                pass
        else:
            try:
                payload = response.json()
                msg = payload.get("message", "")
                # Format is "You reached your request limit. Wait 56 seconds."
                if "Wait" in msg:
                    wait_seconds = float(msg.split("Wait")[1].split("seconds")[0].strip())
            except (ValueError, KeyError, AttributeError):
                pass

        logger.info("Rate limited by football-data.org. Sleeping %.1fs before retry.", wait_seconds)
        time.sleep(wait_seconds + 0.5)
        attempt += 1


def fetch_competitions():
    """Fetch available competitions"""
    url = f"{BASE_URL}/competitions"
    response = _request_get(url)
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
    
    response = _request_get(url, params=params)
    if response.status_code == 200:
        return response.json().get('teams', [])
    print(f"Failed to fetch teams: {response.status_code}")
    return []

def fetch_competition_matches(
    competition_code='PL',
    status=None,
    matchday=None,
    season=None,
    date_from=None,
    date_to=None,
    limit=None,
    stage=None,
    group=None,
):
    """
    Fetch matches for a specific competition.

    status: 'SCHEDULED', 'LIVE', 'FINISHED', or None for all
    matchday: Specific matchday number
    season: Starting year of the season (e.g. 2024 for 2024/25)
    date_from / date_to: 'YYYY-MM-DD' strings
    limit: page size (free tier default is 100)
    stage / group: filter by stage (e.g. GROUP_STAGE) or group (e.g. GROUP_F)

    Without filters, football-data.org applies a default limit (100) and may
    return only a window around the current matchday. Pass `season` and/or
    `date_from`/`date_to` to retrieve the whole season.
    """
    url = f"{BASE_URL}/competitions/{competition_code}/matches"
    params = {}
    if status:
        params['status'] = status
    if matchday:
        params['matchday'] = matchday
    if season is not None:
        params['season'] = season
    if date_from:
        params['dateFrom'] = date_from
    if date_to:
        params['dateTo'] = date_to
    if limit:
        params['limit'] = limit
    if stage:
        params['stage'] = stage
    if group:
        params['group'] = group

    response = _request_get(url, params=params)
    if response.status_code == 200:
        return response.json().get('matches', [])
    print(f"Failed to fetch matches: {response.status_code} - {response.text}")
    return []


def _current_season_year():
    """Return the football season starting year (e.g. 2024 for 2024/25)."""
    today = datetime.now()
    # European seasons start around July/August. Anything before July still
    # belongs to the previous season (e.g. May 2025 -> 2024/25 season).
    return today.year if today.month >= 7 else today.year - 1


def fetch_competition_season_matches(
    competition_code='PL',
    season=None,
    chunk_days=60,
):
    """
    Fetch ALL matches for a competition across an entire season.

    football-data.org's free tier applies a default `limit=100` on the matches
    subresource and may also pre-filter by date when no filters are provided,
    so a single unfiltered call commonly returns only a slice of the season.
    To work around that, we chunk by date range (default 60 days) and merge.

    season: starting year of the season (defaults to the current season).
    chunk_days: size of each date window. Smaller values make more API calls
        but keep each response well under the 100-row limit.
    """
    from datetime import timedelta

    if season is None:
        season = _current_season_year()

    # Resolve season boundaries from the competition resource so we don't have
    # to hardcode them per league. Falls back to a sensible August..July range.
    season_start, season_end = _resolve_season_window(competition_code, season)

    seen_ids = set()
    all_matches = []
    cursor = season_start

    while cursor <= season_end:
        window_end = min(cursor + timedelta(days=chunk_days - 1), season_end)
        chunk = fetch_competition_matches(
            competition_code=competition_code,
            season=season,
            date_from=cursor.strftime('%Y-%m-%d'),
            date_to=window_end.strftime('%Y-%m-%d'),
        )
        for match in chunk:
            mid = match.get('id')
            if mid is None or mid in seen_ids:
                continue
            seen_ids.add(mid)
            all_matches.append(match)
        cursor = window_end + timedelta(days=1)

    return all_matches


def _resolve_season_window(competition_code, season):
    """
    Look up the competition resource and find the start/end dates for the
    requested season. Falls back to August 1st .. July 31st of the next year
    if the API doesn't expose the dates (or the season isn't listed).
    """
    from datetime import date

    fallback_start = date(season, 8, 1)
    fallback_end = date(season + 1, 7, 31)

    try:
        url = f"{BASE_URL}/competitions/{competition_code}"
        response = _request_get(url, timeout=10)
        if response.status_code != 200:
            return fallback_start, fallback_end

        payload = response.json()
        seasons = payload.get('seasons') or []
        # Try to find the requested season by its starting year.
        for s in seasons:
            start_str = s.get('startDate')
            if not start_str:
                continue
            if start_str.startswith(str(season)):
                end_str = s.get('endDate') or fallback_end.isoformat()
                return (
                    datetime.strptime(start_str, '%Y-%m-%d').date(),
                    datetime.strptime(end_str, '%Y-%m-%d').date(),
                )

        # Otherwise fall back to currentSeason if it matches.
        current = payload.get('currentSeason') or {}
        cs_start = current.get('startDate')
        if cs_start and cs_start.startswith(str(season)):
            cs_end = current.get('endDate') or fallback_end.isoformat()
            return (
                datetime.strptime(cs_start, '%Y-%m-%d').date(),
                datetime.strptime(cs_end, '%Y-%m-%d').date(),
            )
    except Exception as exc:
        print(f"  ⚠️ Could not resolve season window for {competition_code}/{season}: {exc}")

    return fallback_start, fallback_end

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
    
    response = _request_get(url, params=params)
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
    
    response = _request_get(url, params=params)
    if response.status_code == 200:
        return response.json().get('matches', [])
    print(f"Failed to fetch team matches: {response.status_code}")
    return []

def fetch_competition_standings(competition_code='PL'):
    """Fetch current standings for a competition"""
    url = f"{BASE_URL}/competitions/{competition_code}/standings"
    response = _request_get(url)
    if response.status_code == 200:
        return response.json().get('standings', [])
    print(f"Failed to fetch standings: {response.status_code}")
    return []

def fetch_competition_scorers(competition_code='PL'):
    """Fetch top scorers for a competition"""
    url = f"{BASE_URL}/competitions/{competition_code}/scorers"
    response = _request_get(url)
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

    # Pull elapsed minute when reported. football-data.org occasionally
    # exposes it inline on /competitions/{code}/matches, but most of the
    # time it ships only on /matches/{id}. We treat it as best-effort:
    # when missing, the persistence layer falls back to a derived value.
    raw_minute = match_data.get('minute') or match_data.get('elapsed')
    try:
        current_minute = int(raw_minute) if raw_minute is not None else None
    except (TypeError, ValueError):
        current_minute = None

    return {
        'fixture': {
            'id': match_data['id'],
            'date': match_data['utcDate'],
            'status': {
                'short': short_status
            },
            'minute': current_minute,
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
