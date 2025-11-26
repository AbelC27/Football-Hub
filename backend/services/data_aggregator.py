import logging
from .api_football_service import api_football
from .thesportsdb_service import thesportsdb

logger = logging.getLogger(__name__)

class DataAggregator:
    def __init__(self):
        pass

    def enrich_player_data(self, player_data):
        """
        Takes a local player object (dict) and adds external data if available.
        """
        enriched = player_data.copy()
        player_name = player_data.get('name')
        
        # 1. Get Photo & Bio from TheSportsDB
        try:
            tsdb_data = thesportsdb.get_player_details(player_name)
            if tsdb_data:
                enriched['photo_url'] = tsdb_data.get('strThumb') or tsdb_data.get('strCutout') or enriched.get('photo_url')
                enriched['date_of_birth'] = tsdb_data.get('dateBorn')
                enriched['nationality'] = tsdb_data.get('strNationality') or enriched.get('nationality')
                enriched['height'] = tsdb_data.get('strHeight') or enriched.get('height')
                enriched['description'] = tsdb_data.get('strDescriptionEN')
        except Exception as e:
            logger.error(f"Aggregator error (TheSportsDB): {e}")

        # 2. Get Stats from API-Football
        try:
            # We assume the current season is 2023 for now, or could make it dynamic
            af_data = api_football.get_player_statistics(player_name, season=2023)
            if af_data:
                stats = af_data.get('statistics', [])[0] if af_data.get('statistics') else {}
                
                enriched['stats'] = {
                    'rating': stats.get('games', {}).get('rating'),
                    'goals': stats.get('goals', {}).get('total'),
                    'assists': stats.get('goals', {}).get('assists'),
                    'minutes_played': stats.get('games', {}).get('minutes'),
                    'team_name': stats.get('team', {}).get('name'),
                    'league_name': stats.get('league', {}).get('name')
                }
        except Exception as e:
            logger.error(f"Aggregator error (API-Football): {e}")

        return enriched

data_aggregator = DataAggregator()
