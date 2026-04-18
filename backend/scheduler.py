import logging
import os
import datetime
from apscheduler.schedulers.background import BackgroundScheduler
from apscheduler.triggers.interval import IntervalTrigger
try:
    from backend.database import SessionLocal
    from backend.services.football_data_org import fetch_competition_matches, parse_match_from_fd
    from backend.models import Match, League, Team
    from backend.generate_predictions import generate_predictions
except ImportError:
    from database import SessionLocal
    from services.football_data_org import fetch_competition_matches, parse_match_from_fd
    from models import Match, League, Team
    from generate_predictions import generate_predictions
import pytz

# Configure logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

COMPETITIONS_TO_REFRESH = [
    code.strip().upper()
    for code in os.getenv("FOOTBALL_DATA_COMPETITIONS", "PL,PD,BL1,SA,FL1").split(",")
    if code.strip()
]


def _parse_fixture_datetime(raw_date: str) -> datetime.datetime:
    """Safely parse API datetime values to timezone-aware datetimes."""
    try:
        return datetime.datetime.fromisoformat(raw_date.replace("Z", "+00:00"))
    except Exception:
        logger.warning("Could not parse fixture date '%s'. Falling back to UTC now.", raw_date)
        return datetime.datetime.now(tz=pytz.UTC)


def _upsert_league(db, league_data):
    league = db.query(League).filter(League.id == league_data["id"]).first()

    if not league:
        league = League(
            id=league_data["id"],
            name=league_data.get("name") or f"League {league_data['id']}",
            country="Unknown",
            logo_url=""
        )
        db.add(league)
        return league

    if league_data.get("name") and league.name != league_data["name"]:
        league.name = league_data["name"]

    return league


def _upsert_team(db, team_data, league_id: int):
    team = db.query(Team).filter(Team.id == team_data["id"]).first()

    if not team:
        team = Team(
            id=team_data["id"],
            name=team_data.get("name") or f"Team {team_data['id']}",
            logo_url=team_data.get("logo") or "",
            stadium="Unknown",
            league_id=league_id
        )
        db.add(team)
        return team

    if team_data.get("name"):
        team.name = team_data["name"]
    if team_data.get("logo"):
        team.logo_url = team_data["logo"]
    if team.league_id != league_id:
        team.league_id = league_id

    return team


def _sync_competition_matches(db, competition_code: str):
    """Upsert leagues, teams, and matches for a competition."""
    matches_data = fetch_competition_matches(competition_code)
    scanned_count = len(matches_data)
    inserted_count = 0
    updated_count = 0

    for match_data in matches_data:
        parsed = parse_match_from_fd(match_data)

        fixture = parsed["fixture"]
        goals = parsed["goals"]
        teams = parsed["teams"]
        league_data = parsed["league"]

        league = _upsert_league(db, league_data)
        _upsert_team(db, teams["home"], league.id)
        _upsert_team(db, teams["away"], league.id)

        start_time = _parse_fixture_datetime(fixture["date"])
        status = fixture["status"]["short"]

        existing_match = db.query(Match).filter(Match.id == fixture["id"]).first()

        if not existing_match:
            db.add(
                Match(
                    id=fixture["id"],
                    home_team_id=teams["home"]["id"],
                    away_team_id=teams["away"]["id"],
                    start_time=start_time,
                    status=status,
                    home_score=goals["home"],
                    away_score=goals["away"]
                )
            )
            inserted_count += 1
            continue

        changed = False

        if existing_match.home_team_id != teams["home"]["id"]:
            existing_match.home_team_id = teams["home"]["id"]
            changed = True
        if existing_match.away_team_id != teams["away"]["id"]:
            existing_match.away_team_id = teams["away"]["id"]
            changed = True
        if existing_match.start_time != start_time:
            existing_match.start_time = start_time
            changed = True
        if existing_match.status != status:
            existing_match.status = status
            changed = True
        if existing_match.home_score != goals["home"]:
            existing_match.home_score = goals["home"]
            changed = True
        if existing_match.away_score != goals["away"]:
            existing_match.away_score = goals["away"]
            changed = True

        if changed:
            updated_count += 1

    return scanned_count, inserted_count, updated_count

def update_live_matches():
    """
    Sync matches from football-data.org for configured competitions.
    This keeps fixtures fresh by both inserting new matches and updating existing ones.
    """
    logger.info("Starting match sync for competitions: %s", ", ".join(COMPETITIONS_TO_REFRESH))
    db = SessionLocal()

    total_scanned = 0
    total_inserted = 0
    total_updated = 0

    try:
        for competition_code in COMPETITIONS_TO_REFRESH:
            try:
                scanned, inserted, updated = _sync_competition_matches(db, competition_code)
                db.commit()

                total_scanned += scanned
                total_inserted += inserted
                total_updated += updated
            except Exception:
                db.rollback()
                logger.exception("Failed to sync competition %s", competition_code)

        logger.info(
            "Match sync finished. scanned=%s inserted=%s updated=%s",
            total_scanned,
            total_inserted,
            total_updated
        )
    except Exception as e:
        db.rollback()
        logger.error(f"Error updating matches: {e}")
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
    scheduler = BackgroundScheduler(timezone=pytz.UTC)
    
    # Update matches every 60 seconds and run immediately at startup.
    scheduler.add_job(
        update_live_matches,
        trigger=IntervalTrigger(seconds=60),
        id='update_live_matches',
        name='Update Live Matches',
        replace_existing=True,
        next_run_time=datetime.datetime.now(tz=pytz.UTC)
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
