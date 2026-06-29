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
    for code in os.getenv("FOOTBALL_DATA_COMPETITIONS", "PL,PD,BL1,SA,FL1,WC").split(",")
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
                    league_id=league.id,
                    start_time=start_time,
                    status=status,
                    home_score=goals["home"],
                    away_score=goals["away"],
                    current_minute=current_minute,
                    stage=fixture.get("stage"),
                    group_name=fixture.get("group_name"),
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

        if existing_match.league_id != league.id:
            existing_match.league_id = league.id
            changed = True
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

        # Tournament metadata (stage / group) — update if provided
        new_stage = fixture.get("stage")
        new_group = fixture.get("group_name")
        if new_stage and existing_match.stage != new_stage:
            existing_match.stage = new_stage
            changed = True
        if new_group and existing_match.group_name != new_group:
            existing_match.group_name = new_group
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


def enrich_wc_match_stats():
    """Fetch match statistics from API-Football for recently finished WC matches."""
    try:
        from services.apisports import (
            get_wc_fixtures_by_date, get_fixture_statistics,
            calls_used_today, ApisportsQuotaExceeded,
        )
    except ImportError:
        try:
            from backend.services.apisports import (
                get_wc_fixtures_by_date, get_fixture_statistics,
                calls_used_today, ApisportsQuotaExceeded,
            )
        except ImportError:
            logger.warning("apisports module not available for WC enrichment")
            return

    try:
        from models import MatchStatistics
    except ImportError:
        from backend.models import MatchStatistics

    if calls_used_today() >= 90:
        logger.info("WC enrichment skipped: API-Football budget near limit (%d/100)", calls_used_today())
        return

    WC_LEAGUE_ID = 2000
    db = SessionLocal()
    try:
        # Find recently finished WC matches without stats
        finished_wc = (
            db.query(Match)
            .filter(
                Match.league_id == WC_LEAGUE_ID,
                Match.status.in_(list({"FT", "AET", "PEN"})),
            )
            .all()
        )

        matches_needing_stats = []
        for m in finished_wc:
            has_stats = db.query(MatchStatistics).filter(MatchStatistics.match_id == m.id).first()
            if not has_stats:
                matches_needing_stats.append(m)

        if not matches_needing_stats:
            return

        logger.info("WC enrichment: %d matches need stats", len(matches_needing_stats))

        for match in matches_needing_stats:
            if calls_used_today() >= 90:
                break

            # Find API-Football fixture by date
            match_date = match.start_time.strftime("%Y-%m-%d") if match.start_time else None
            if not match_date:
                continue

            try:
                fixtures = get_wc_fixtures_by_date(match_date)
            except ApisportsQuotaExceeded:
                break

            # Match by team names
            home_team = db.query(Team).filter(Team.id == match.home_team_id).first()
            away_team = db.query(Team).filter(Team.id == match.away_team_id).first()
            if not home_team or not away_team:
                continue

            af_fixture_id = None
            home_name_lower = home_team.name.lower()
            away_name_lower = away_team.name.lower()

            for fx in fixtures:
                fx_teams = fx.get("teams", {})
                fx_home = (fx_teams.get("home", {}).get("name") or "").lower()
                fx_away = (fx_teams.get("away", {}).get("name") or "").lower()
                if (home_name_lower in fx_home or fx_home in home_name_lower) and \
                   (away_name_lower in fx_away or fx_away in away_name_lower):
                    af_fixture_id = fx.get("fixture", {}).get("id")
                    break

            if not af_fixture_id:
                continue

            try:
                stats_resp = get_fixture_statistics(af_fixture_id)
            except ApisportsQuotaExceeded:
                break

            if len(stats_resp) < 2:
                continue

            def _stat_val(team_stats, stat_name):
                for s in team_stats.get("statistics", []):
                    if s.get("type") == stat_name:
                        val = s.get("value")
                        if isinstance(val, str):
                            val = val.replace("%", "")
                        try:
                            return int(val) if val is not None else 0
                        except (ValueError, TypeError):
                            return 0
                return 0

            home_stats = stats_resp[0]
            away_stats = stats_resp[1]

            db.add(MatchStatistics(
                match_id=match.id,
                possession_home=_stat_val(home_stats, "Ball Possession"),
                possession_away=_stat_val(away_stats, "Ball Possession"),
                shots_on_home=_stat_val(home_stats, "Shots on Goal"),
                shots_on_away=_stat_val(away_stats, "Shots on Goal"),
                shots_off_home=_stat_val(home_stats, "Shots off Goal"),
                shots_off_away=_stat_val(away_stats, "Shots off Goal"),
                corners_home=_stat_val(home_stats, "Corner Kicks"),
                corners_away=_stat_val(away_stats, "Corner Kicks"),
                fouls_home=_stat_val(home_stats, "Fouls"),
                fouls_away=_stat_val(away_stats, "Fouls"),
            ))
            db.commit()
            logger.info("WC enrichment: stats saved for match %d", match.id)

    except Exception:
        db.rollback()
        logger.exception("WC enrichment failed")
    finally:
        db.close()


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

    # WC match stats enrichment — runs every 10 minutes, budget-aware
    scheduler.add_job(
        enrich_wc_match_stats,
        trigger=IntervalTrigger(minutes=10),
        id='enrich_wc_stats',
        name='WC Match Stats Enrichment',
        replace_existing=True,
    )

    scheduler.start()
    logger.info("Background scheduler started.")
    return scheduler
