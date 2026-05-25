"""
Backfill match event minutes AND match statistics from Football-Data.org API.

This script fetches individual match details from football-data.org to get:
- Goal minutes (+ scorer, assist info)
- Booking minutes (yellow/red cards)
- Match statistics (possession, shots, corners, fouls, saves, offsides, etc.)

Usage:
    cd backend
    .venv/bin/python -m scripts.backfill_event_minutes

Notes:
    - Free tier: 10 requests/minute. The script respects this via the existing
      rate limiter in services.football_data_org.
    - With ~2000 matches this will take ~3.5 hours. Run it in background.
    - Only processes matches that need data (events with minute=None OR missing stats).
    - Safe to re-run: skips matches already fully backfilled.
"""

import logging
import sys
import time

from sqlalchemy import func
from sqlalchemy.orm import Session

try:
    from backend.database import SessionLocal
    from backend.models import Match, MatchEvent, MatchStatistics
    from backend.services.football_data_org import _request_get, BASE_URL
except ImportError:
    from database import SessionLocal
    from models import Match, MatchEvent, MatchStatistics
    from services.football_data_org import _request_get, BASE_URL

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(message)s",
    handlers=[logging.StreamHandler(sys.stdout)],
)
logger = logging.getLogger(__name__)


def _normalize(name: str) -> str:
    """Lowercase, strip for fuzzy name matching."""
    if not name:
        return ""
    return name.strip().lower()


def _match_player_name(event_name: str, api_name: str) -> bool:
    """Fuzzy match: check if one name contains the other or last names match."""
    en = _normalize(event_name)
    an = _normalize(api_name)
    if not en or not an:
        return False
    if en == an:
        return True
    # Check if last name matches
    en_last = en.split()[-1] if en.split() else en
    an_last = an.split()[-1] if an.split() else an
    if en_last == an_last and len(en_last) > 2:
        return True
    # Check containment
    if en in an or an in en:
        return True
    return False


def fetch_match_details(match_id: int) -> dict | None:
    """Fetch full match details from football-data.org /v4/matches/{id}."""
    url = f"{BASE_URL}/matches/{match_id}"
    try:
        response = _request_get(url)
        if response.status_code == 200:
            return response.json()
        elif response.status_code == 403:
            logger.warning(
                "Match %d: 403 Forbidden (free tier may not allow this endpoint). Skipping.",
                match_id,
            )
            return None
        elif response.status_code == 404:
            logger.debug("Match %d: not found on football-data.org.", match_id)
            return None
        else:
            logger.warning(
                "Match %d: unexpected status %d. Skipping.", match_id, response.status_code
            )
            return None
    except Exception as exc:
        logger.error("Match %d: request failed: %s", match_id, exc)
        return None


def backfill_events(db: Session, match: Match, api_data: dict) -> int:
    """
    Update MatchEvent rows for a single match using API goal/booking data.
    Returns number of events updated.
    """
    updated = 0

    # Get existing events without minutes for this match
    events = (
        db.query(MatchEvent)
        .filter(MatchEvent.match_id == match.id, MatchEvent.minute.is_(None))
        .all()
    )

    if not events:
        return 0

    # Build lookup from API data
    api_goals = api_data.get("goals") or []
    api_bookings = api_data.get("bookings") or []

    # Map team IDs from football-data.org to local team IDs
    home_team_fd_id = (api_data.get("homeTeam") or {}).get("id")
    away_team_fd_id = (api_data.get("awayTeam") or {}).get("id")

    fd_to_local_team = {}
    if home_team_fd_id:
        fd_to_local_team[home_team_fd_id] = match.home_team_id
    if away_team_fd_id:
        fd_to_local_team[away_team_fd_id] = match.away_team_id

    # Process goal events
    goal_events = [e for e in events if e.event_type == "Goal"]
    used_api_goals = set()

    for event in goal_events:
        best_match_idx = None
        for idx, api_goal in enumerate(api_goals):
            if idx in used_api_goals:
                continue
            scorer_name = (api_goal.get("scorer") or {}).get("name", "")
            api_team_id = (api_goal.get("team") or {}).get("id")
            local_team_id = fd_to_local_team.get(api_team_id)

            if _match_player_name(event.player_name or "", scorer_name):
                if local_team_id is None or local_team_id == event.team_id:
                    best_match_idx = idx
                    break

        if best_match_idx is not None:
            event.minute = api_goals[best_match_idx].get("minute")
            used_api_goals.add(best_match_idx)
            if event.minute is not None:
                updated += 1

    # Process assist events
    assist_events = [e for e in events if e.event_type == "Assist"]
    used_api_assists = set()

    for event in assist_events:
        best_match_idx = None
        for idx, api_goal in enumerate(api_goals):
            if idx in used_api_assists:
                continue
            assist_info = api_goal.get("assist")
            if not assist_info or not assist_info.get("name"):
                continue
            assist_name = assist_info["name"]
            api_team_id = (api_goal.get("team") or {}).get("id")
            local_team_id = fd_to_local_team.get(api_team_id)

            if _match_player_name(event.player_name or "", assist_name):
                if local_team_id is None or local_team_id == event.team_id:
                    best_match_idx = idx
                    break

        if best_match_idx is not None:
            event.minute = api_goals[best_match_idx].get("minute")
            used_api_assists.add(best_match_idx)
            if event.minute is not None:
                updated += 1

    # Process card events
    card_events = [e for e in events if e.event_type == "Card"]
    used_api_bookings = set()

    for event in card_events:
        best_match_idx = None
        for idx, api_booking in enumerate(api_bookings):
            if idx in used_api_bookings:
                continue
            player_name = (api_booking.get("player") or {}).get("name", "")
            api_team_id = (api_booking.get("team") or {}).get("id")
            local_team_id = fd_to_local_team.get(api_team_id)

            if _match_player_name(event.player_name or "", player_name):
                if local_team_id is None or local_team_id == event.team_id:
                    best_match_idx = idx
                    break

        if best_match_idx is not None:
            event.minute = api_bookings[best_match_idx].get("minute")
            used_api_bookings.add(best_match_idx)
            if event.minute is not None:
                updated += 1

    return updated


def backfill_statistics(db: Session, match: Match, api_data: dict) -> bool:
    """
    Create or update MatchStatistics row from API team statistics.
    Returns True if a row was created/updated.

    football-data.org provides per-team statistics:
        corner_kicks, free_kicks, goal_kicks, offsides, fouls,
        ball_possession, saves, throw_ins, shots, shots_on_goal,
        shots_off_goal, yellow_cards, yellow_red_cards, red_cards
    """
    home_stats = (api_data.get("homeTeam") or {}).get("statistics")
    away_stats = (api_data.get("awayTeam") or {}).get("statistics")

    if not home_stats and not away_stats:
        return False

    # Check if we already have stats for this match
    existing = db.query(MatchStatistics).filter(MatchStatistics.match_id == match.id).first()

    if existing:
        # Already have stats — skip
        return False

    def _safe_int(val):
        if val is None:
            return None
        try:
            return int(val)
        except (TypeError, ValueError):
            return None

    home = home_stats or {}
    away = away_stats or {}

    stats = MatchStatistics(
        match_id=match.id,
        possession_home=_safe_int(home.get("ball_possession")),
        possession_away=_safe_int(away.get("ball_possession")),
        shots_on_home=_safe_int(home.get("shots_on_goal")),
        shots_on_away=_safe_int(away.get("shots_on_goal")),
        shots_off_home=_safe_int(home.get("shots_off_goal")),
        shots_off_away=_safe_int(away.get("shots_off_goal")),
        corners_home=_safe_int(home.get("corner_kicks")),
        corners_away=_safe_int(away.get("corner_kicks")),
        fouls_home=_safe_int(home.get("fouls")),
        fouls_away=_safe_int(away.get("fouls")),
    )

    db.add(stats)
    return True


def main():
    db = SessionLocal()
    try:
        # Find all finished matches — we want both events and stats
        finished_matches = (
            db.query(Match)
            .filter(Match.status.in_(["FT", "AET", "PEN"]))
            .order_by(Match.id.asc())
            .all()
        )

        if not finished_matches:
            logger.info("No finished matches found. Nothing to backfill.")
            return

        # Determine which matches need work:
        # 1. Matches with events that have minute=None
        match_ids_needing_minutes = set(
            row[0]
            for row in db.query(MatchEvent.match_id)
            .filter(MatchEvent.minute.is_(None))
            .distinct()
            .all()
        )

        # 2. Matches without statistics
        match_ids_with_stats = set(
            row[0]
            for row in db.query(MatchStatistics.match_id).all()
        )

        matches_to_process = [
            m for m in finished_matches
            if m.id in match_ids_needing_minutes or m.id not in match_ids_with_stats
        ]

        if not matches_to_process:
            logger.info("All matches already have minutes and statistics. Nothing to do.")
            return

        logger.info(
            "Found %d finished matches needing backfill (%d need minutes, %d need stats).",
            len(matches_to_process),
            len(match_ids_needing_minutes),
            len(finished_matches) - len(match_ids_with_stats),
        )

        total_events_updated = 0
        total_stats_created = 0
        processed = 0
        failed = 0

        for i, match in enumerate(matches_to_process, 1):
            api_data = fetch_match_details(match.id)

            if api_data is None:
                failed += 1
                if i % 50 == 0:
                    logger.info(
                        "Progress: %d/%d (events_updated=%d, stats_created=%d, failed=%d)",
                        i, len(matches_to_process), total_events_updated, total_stats_created, failed,
                    )
                continue

            # Backfill event minutes
            events_updated = 0
            if match.id in match_ids_needing_minutes:
                events_updated = backfill_events(db, match, api_data)
                total_events_updated += events_updated

            # Backfill statistics
            stats_created = backfill_statistics(db, match, api_data)
            if stats_created:
                total_stats_created += 1

            # Commit every match to avoid losing progress on crash
            if events_updated > 0 or stats_created:
                db.commit()

            processed += 1

            if i % 20 == 0:
                logger.info(
                    "Progress: %d/%d (events_updated=%d, stats_created=%d, failed=%d)",
                    i, len(matches_to_process), total_events_updated, total_stats_created, failed,
                )

        # Final commit for any remaining changes
        db.commit()

        logger.info(
            "Backfill complete. Processed=%d, Events updated=%d, Stats created=%d, Failed=%d",
            processed, total_events_updated, total_stats_created, failed,
        )

    finally:
        db.close()


if __name__ == "__main__":
    main()
