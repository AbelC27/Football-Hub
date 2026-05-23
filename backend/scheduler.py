import logging
import os
import datetime
from typing import Dict, List, Optional

from apscheduler.schedulers.background import BackgroundScheduler
from apscheduler.triggers.interval import IntervalTrigger
try:
    from backend.database import SessionLocal
    from backend.services.football_data_org import (
        fetch_competition_matches,
        fetch_competition_season_matches,
        parse_match_from_fd,
    )
    from backend.models import Match, League, Team
    from backend.generate_predictions import generate_predictions
    from backend.services.news_triggers import run_post_match_news, run_pre_derby_news
    from backend.services.live_broadcaster import enqueue_match_updates
except ImportError:
    from database import SessionLocal
    from services.football_data_org import (
        fetch_competition_matches,
        fetch_competition_season_matches,
        parse_match_from_fd,
    )
    from models import Match, League, Team
    from generate_predictions import generate_predictions
    from services.news_triggers import run_post_match_news, run_pre_derby_news
    from services.live_broadcaster import enqueue_match_updates
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


LIVE_STATUSES = {"LIVE", "HT", "ET", "P", "1H", "2H"}


def _derive_live_minute(start_time: datetime.datetime) -> Optional[int]:
    """
    Estimate elapsed minutes when the provider doesn't expose `minute`.
    Naive: doesn't know about HT/ET/stoppages, but always better than `None`
    on the UI. Clamped to 1..120.
    """
    if start_time is None:
        return None
    now = datetime.datetime.now(tz=pytz.UTC)
    if start_time.tzinfo is None:
        start_time = start_time.replace(tzinfo=pytz.UTC)
    elapsed = int((now - start_time).total_seconds() // 60)
    if elapsed < 1:
        return None
    return max(1, min(elapsed, 120))


def _persist_matches(db, matches_data):
    scanned_count = len(matches_data)
    inserted_count = 0
    updated_count = 0
    broadcast_payloads: List[Dict[str, object]] = []

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
        provider_minute = fixture.get("minute")

        if status in LIVE_STATUSES:
            current_minute = (
                provider_minute
                if provider_minute is not None
                else _derive_live_minute(start_time)
            )
        else:
            current_minute = None

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
                    away_score=goals["away"],
                    current_minute=current_minute,
                )
            )
            inserted_count += 1
            if status in LIVE_STATUSES:
                broadcast_payloads.append(
                    {
                        "match_id": fixture["id"],
                        "status": status,
                        "home_score": goals["home"],
                        "away_score": goals["away"],
                        "current_minute": current_minute,
                    }
                )
            continue

        changed = False
        score_or_status_changed = False

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
            score_or_status_changed = True
        if existing_match.home_score != goals["home"]:
            existing_match.home_score = goals["home"]
            changed = True
            score_or_status_changed = True
        if existing_match.away_score != goals["away"]:
            existing_match.away_score = goals["away"]
            changed = True
            score_or_status_changed = True
        if existing_match.current_minute != current_minute:
            existing_match.current_minute = current_minute
            changed = True

        if changed:
            updated_count += 1

        # Push any update for currently-live matches (so the timer ticks),
        # plus any state transition (kickoff, goal, FT) regardless of liveness.
        if status in LIVE_STATUSES or score_or_status_changed:
            broadcast_payloads.append(
                {
                    "match_id": fixture["id"],
                    "status": status,
                    "home_score": goals["home"],
                    "away_score": goals["away"],
                    "current_minute": current_minute,
                }
            )

    return scanned_count, inserted_count, updated_count, broadcast_payloads


def _sync_competition_live_window(db, competition_code: str):
    """
    Lightweight, frequent sync: covers a rolling window that reaches a few
    days into the past and one day into the future.

    The backward reach matters: if a match transitions NS -> FT while we
    were offline (or the provider published the FT status late), a tight
    +/-1 day window would never see it again and the row would stay stuck
    on `NS` forever. We default to a 7-day lookback so the next sync after
    a downtime catches every recent fixture, while staying well under the
    free-tier 100-row response cap.
    """
    today = datetime.datetime.utcnow().date()
    lookback_days = int(os.getenv("FOOTBALL_DATA_SYNC_LOOKBACK_DAYS", "7"))
    lookahead_days = int(os.getenv("FOOTBALL_DATA_SYNC_LOOKAHEAD_DAYS", "1"))
    date_from = (today - datetime.timedelta(days=lookback_days)).strftime("%Y-%m-%d")
    date_to = (today + datetime.timedelta(days=lookahead_days)).strftime("%Y-%m-%d")
    matches_data = fetch_competition_matches(
        competition_code,
        date_from=date_from,
        date_to=date_to,
    )
    return _persist_matches(db, matches_data)


def _sync_competition_full_season(db, competition_code: str):
    """Full-season sync: pulls every match for the current season via chunking."""
    matches_data = fetch_competition_season_matches(competition_code)
    return _persist_matches(db, matches_data)

def update_live_matches():
    logger.info("Starting live-window sync for competitions: %s", ", ".join(COMPETITIONS_TO_REFRESH))
    db = SessionLocal()

    total_scanned = 0
    total_inserted = 0
    total_updated = 0
    aggregated_broadcasts: List[Dict[str, object]] = []

    try:
        for competition_code in COMPETITIONS_TO_REFRESH:
            try:
                scanned, inserted, updated, broadcasts = _sync_competition_live_window(db, competition_code)
                db.commit()

                total_scanned += scanned
                total_inserted += inserted
                total_updated += updated
                aggregated_broadcasts.extend(broadcasts)
            except Exception:
                db.rollback()
                logger.exception("Failed live-window sync for competition %s", competition_code)

        logger.info(
            "Live-window sync finished. scanned=%s inserted=%s updated=%s",
            total_scanned,
            total_inserted,
            total_updated
        )

        if aggregated_broadcasts:
            try:
                enqueue_match_updates(aggregated_broadcasts)
            except Exception:
                # Broadcast best-effort: never let a WS issue break the sync.
                logger.exception("Failed to enqueue %s live updates", len(aggregated_broadcasts))
    except Exception:
        db.rollback()
        logger.exception("Error updating live matches")
    finally:
        db.close()


def sync_full_season():
    """
    Full-season sync for all configured competitions. Heavier on API quota
    (chunks the season into ~60-day windows), so it runs at startup and once
    per day rather than every minute.
    """
    logger.info("Starting full-season sync for competitions: %s", ", ".join(COMPETITIONS_TO_REFRESH))
    db = SessionLocal()

    total_scanned = 0
    total_inserted = 0
    total_updated = 0

    try:
        for competition_code in COMPETITIONS_TO_REFRESH:
            try:
                scanned, inserted, updated, _broadcasts = _sync_competition_full_season(db, competition_code)
                db.commit()

                total_scanned += scanned
                total_inserted += inserted
                total_updated += updated
            except Exception:
                db.rollback()
                logger.exception("Failed full-season sync for competition %s", competition_code)

        logger.info(
            "Full-season sync finished. scanned=%s inserted=%s updated=%s",
            total_scanned,
            total_inserted,
            total_updated
        )
    except Exception:
        db.rollback()
        logger.exception("Error during full-season sync")
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


def run_weekly_model_retraining():
    """Weekly retrain of the 1X2 match-outcome model.

    Steps (executed in a worker thread):
      1. Rebuild Elo snapshots from the latest finished matches.
      2. Re-run the training pipeline (temporal split, isotonic, baselines).
      3. Persist the new artifacts. The inference singleton picks up the
         changes via its `mtime` cache without requiring a server restart.

    Failure here never crashes the scheduler; we just log the trace and
    keep serving predictions from the previously-trained artifacts.
    """
    logger.info("Starting weekly retraining of match-outcome model...")
    try:
        # Imported lazily so a missing AI dependency never breaks the
        # rest of the scheduler.
        try:
            from backend.ai.build_elo_history import main as rebuild_elo
            from backend.ai.train import main as train_model
        except ImportError:
            from ai.build_elo_history import main as rebuild_elo  # type: ignore[no-redef]
            from ai.train import main as train_model  # type: ignore[no-redef]

        rebuild_elo()
        train_model()
        logger.info("Weekly retraining completed.")
    except Exception:
        logger.exception("Weekly retraining failed (artifacts left untouched)")

def start_scheduler():
    scheduler = BackgroundScheduler(timezone=pytz.UTC)
    if os.getenv("ENABLE_FULL_SEASON_SYNC", "").strip().lower() in {"1", "true", "yes"}:
        scheduler.add_job(
            sync_full_season,
            trigger=IntervalTrigger(hours=24),
            id='sync_full_season',
            name='Full Season Sync',
            replace_existing=True,
            next_run_time=datetime.datetime.now(tz=pytz.UTC),
        )
        logger.info("Full Season Sync enabled (ENABLE_FULL_SEASON_SYNC=1)")
    else:
        logger.info(
            "Full Season Sync disabled. Run seed_football_data_org.py manually "
            "or set ENABLE_FULL_SEASON_SYNC=1 to re-enable."
        )

    scheduler.add_job(
        update_live_matches,
        trigger=IntervalTrigger(seconds=60),
        id='update_live_matches',
        name='Update Live Matches',
        replace_existing=True,
        next_run_time=datetime.datetime.now(tz=pytz.UTC) + datetime.timedelta(seconds=10),
    )
    
    scheduler.add_job(
        run_predictions,
        trigger=IntervalTrigger(hours=1),
        id='generate_predictions',
        name='Generate Predictions',
        replace_existing=True
    )

    scheduler.add_job(
        run_post_match_news,
        trigger=IntervalTrigger(minutes=5),
        id='ai_news_post_match',
        name='AI News - Post Match',
        replace_existing=True,
    )

    scheduler.add_job(
        run_pre_derby_news,
        trigger=IntervalTrigger(hours=1),
        id='ai_news_pre_derby',
        name='AI News - Pre Derby',
        replace_existing=True,
    )

    # Retrain the 1X2 match-outcome model once per week. Cheap to run
    # (~30s on the current dataset) and ensures the network stays in sync
    # with new finished matches and updated Elo ratings without manual
    # intervention. Disabled when ENABLE_WEEKLY_RETRAIN=0 to make local
    # development less noisy.
    if os.getenv("ENABLE_WEEKLY_RETRAIN", "1").strip().lower() not in {"0", "false", "no"}:
        scheduler.add_job(
            run_weekly_model_retraining,
            trigger=IntervalTrigger(days=7),
            id='retrain_match_outcome_model',
            name='Retrain 1X2 Model',
            replace_existing=True,
        )
        logger.info("Weekly model retraining job registered.")

    scheduler.start()
    logger.info("Background scheduler started.")
    return scheduler
