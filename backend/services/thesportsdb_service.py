import os
import requests
import logging

logger = logging.getLogger(__name__)

class TheSportsDBService:
    def __init__(self):
        self.api_key = os.getenv("THESPORTSDB_KEY", "3") # '3' is the free test key
        self.base_url = "https://www.thesportsdb.com/api/v1/json"

    def get_player_details(self, player_name: str):
        """
        Get player details including photo (thumb) and description.
        """
        try:
            url = f"{self.base_url}/{self.api_key}/searchplayers.php?p={player_name}"
            response = requests.get(url)
            
            if response.status_code == 200:
                data = response.json()
                if data and data.get('player'):
                    # Return the first match
                    return data['player'][0]
            
            return None
        except Exception as e:
            logger.error(f"Error fetching TheSportsDB data: {e}")
            return None

    def get_team_details(self, team_name: str):
        """
        Get team details including high-res badge.
        """
        try:
            url = f"{self.base_url}/{self.api_key}/searchteams.php?t={team_name}"
            response = requests.get(url)
            
            if response.status_code == 200:
                data = response.json()
                if data and data.get('teams'):
                    return data['teams'][0]
            
            return None
        except Exception as e:
            logger.error(f"Error fetching TheSportsDB team data: {e}")
            return None

thesportsdb = TheSportsDBService()
