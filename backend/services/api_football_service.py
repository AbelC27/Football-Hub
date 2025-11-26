import os
import requests
import logging

logger = logging.getLogger(__name__)

class APIFootballService:
    def __init__(self):
        self.api_key = os.getenv("API_FOOTBALL_KEY")
        self.base_url = "https://v3.football.api-sports.io"
        self.headers = {
            'x-rapidapi-host': "v3.football.api-sports.io",
            'x-rapidapi-key': self.api_key
        }

    def get_player_statistics(self, player_name: str, team_name: str = None, season: int = 2023):
        """
        Search for a player and get their statistics.
        Since we don't have the API-Football player ID mapping, we search by name.
        """
        if not self.api_key:
            return None

        try:
            # Search for player
            params = {'search': player_name, 'season': season}
            if team_name:
                # Note: Team filtering in search might not be direct in all endpoints, 
                # but we can filter results.
                pass

            response = requests.get(f"{self.base_url}/players", headers=self.headers, params=params)
            
            if response.status_code == 200:
                data = response.json()
                if data['results'] > 0:
                    # Return the first match's statistics
                    # In a real app, we'd want better matching logic (e.g. check team name)
                    return data['response'][0]
            
            return None
        except Exception as e:
            logger.error(f"Error fetching API-Football data: {e}")
            return None

api_football = APIFootballService()
