from database import SessionLocal
from services.data_ingestion import fetch_leagues, fetch_teams, fetch_fixtures, fetch_match_events, fetch_match_statistics
from models import League, Team, Match, MatchEvent, MatchStatistics
from datetime import datetime, timedelta
import time

def seed_events_and_statistics():
    """Seed match events and statistics for recent matches"""
    db = SessionLocal()
    try:
        print("Seeding Match Events and Statistics...")
        
        # Get matches from the last 7 days with status FT (Full Time)
        seven_days_ago = datetime.now() - timedelta(days=7)
        recent_matches = db.query(Match).filter(
            Match.start_time >= seven_days_ago,
            Match.status == 'FT'
        ).limit(10).all()  # Limit to 10 matches to save API calls
        
        print(f"Found {len(recent_matches)} recent finished matches")
        
        for match in recent_matches:
            print(f"Fetching data for match {match.id}...")
            
            # Fetch and store events
            events_data = fetch_match_events(match.id)
            for event in events_data:
                event_type = event['type']
                team_id = event['team']['id']
                player_name = event['player']['name'] if event.get('player') else 'Unknown'
                minute = event['time']['elapsed']
                detail = event.get('detail', '')
                
                # Check if event already exists
                existing = db.query(MatchEvent).filter(
                    MatchEvent.match_id == match.id,
                    MatchEvent.minute == minute,
                    MatchEvent.event_type == event_type,
                    MatchEvent.player_name == player_name
                ).first()
                
                if not existing:
                    match_event = MatchEvent(
                        match_id=match.id,
                        minute=minute,
                        event_type=event_type,
                        team_id=team_id,
                        player_name=player_name,
                        detail=detail
                    )
                    db.add(match_event)
            
            # Fetch and store statistics
            stats_data = fetch_match_statistics(match.id)
            if len(stats_data) >= 2:  # Should have stats for both teams
                home_stats = stats_data[0]['statistics'] if stats_data[0]['team']['id'] == match.home_team_id else stats_data[1]['statistics']
                away_stats = stats_data[1]['statistics'] if stats_data[1]['team']['id'] == match.away_team_id else stats_data[0]['statistics']
                
                # Helper function to extract stat value
                def get_stat(stats_list, stat_type):
                    for stat in stats_list:
                        if stat['type'] == stat_type:
                            value = stat['value']
                            if value is None:
                                return None
                            if isinstance(value, str) and '%' in value:
                                return int(value.replace('%', ''))
                            return int(value) if value else None
                    return None
                
                # Check if statistics already exist
                existing_stats = db.query(MatchStatistics).filter(MatchStatistics.match_id == match.id).first()
                
                if not existing_stats:
                    match_stats = MatchStatistics(
                        match_id=match.id,
                        possession_home=get_stat(home_stats, 'Ball Possession'),
                        possession_away=get_stat(away_stats, 'Ball Possession'),
                        shots_on_home=get_stat(home_stats, 'Shots on Goal'),
                        shots_on_away=get_stat(away_stats, 'Shots on Goal'),
                        shots_off_home=get_stat(home_stats, 'Shots off Goal'),
                        shots_off_away=get_stat(away_stats, 'Shots off Goal'),
                        corners_home=get_stat(home_stats, 'Corner Kicks'),
                        corners_away=get_stat(away_stats, 'Corner Kicks'),
                        fouls_home=get_stat(home_stats, 'Fouls'),
                        fouls_away=get_stat(away_stats, 'Fouls')
                    )
                    db.add(match_stats)
            
            db.commit()
            print(f"✅ Stored events and statistics for match {match.id}")
            
            # Sleep to respect rate limits
            time.sleep(1)
        
        print("Events and Statistics seeded successfully!")
        
    finally:
        db.close()

if __name__ == "__main__":
    seed_events_and_statistics()
