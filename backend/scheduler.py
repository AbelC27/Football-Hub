import logging
from apscheduler.schedulers.background import BackgroundScheduler
from apscheduler.triggers.interval import IntervalTrigger
try:
    from backend.database import SessionLocal
    from backend.services.football_data_org import fetch_competition_matches, parse_match_from_fd
    from backend.models import Match
    from backend.generate_predictions import generate_predictions
except ImportError:
    from database import SessionLocal
    from services.football_data_org import fetch_competition_matches, parse_match_from_fd
    from models import Match
    from generate_predictions import generate_predictions
import datetime
import pytz

# Configure logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

def update_live_matches():
    """
    Fetch and update matches that are currently live or scheduled for today.
    """
    logger.info("Starting live match update...")
    db = SessionLocal()
    try:
        # Fetch matches from API (PL = Premier League)
        matches_data = fetch_competition_matches('PL')
        
        updated_count = 0
        for match_data in matches_data:
            parsed = parse_match_from_fd(match_data)
            fixture = parsed['fixture']
            goals = parsed['goals']
            status = fixture['status']['short']
            
            # Update existing match in DB
            existing_match = db.query(Match).filter(Match.id == fixture['id']).first()
            
            if existing_match:
                # Check if anything changed
                if (existing_match.status != status or 
                    existing_match.home_score != goals['home'] or 
                    existing_match.away_score != goals['away']):
                    
                    existing_match.status = status
                    existing_match.home_score = goals['home']
                    existing_match.away_score = goals['away']
                    updated_count += 1
        
        db.commit()
        if updated_count > 0:
            logger.info(f"Updated {updated_count} matches with new data.")
        else:
            logger.info("No match updates found.")
            
    except Exception as e:
        logger.error(f"Error updating live matches: {e}")
    finally:
        db.close()

def run_predictions():
    """Wrapper for prediction generation with logging"""
    logger.info("Starting scheduled prediction generation...")
    try:
        generate_predictions()
        logger.info("Prediction generation completed.")
    except Exception as e:
        logger.error(f"Error generating predictions: {e}")

def start_scheduler():
    scheduler = BackgroundScheduler()
    
    # Update matches every 60 seconds
    scheduler.add_job(
        update_live_matches,
        trigger=IntervalTrigger(seconds=60),
        id='update_live_matches',
        name='Update Live Matches',
        replace_existing=True
    )
    
    # Generate predictions every hour
    scheduler.add_job(
        run_predictions,
        trigger=IntervalTrigger(hours=1),
        id='generate_predictions',
        name='Generate Predictions',
        replace_existing=True
    )
    
    scheduler.start()
    logger.info("Background scheduler started.")
    return scheduler
