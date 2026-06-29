"""
Fetch detailed match data (goals, lineups, bookings, substitutions) for World Cup matches
from football-data.org single match endpoint and persist to MatchEvent table.

Run: python seed_wc_match_details.py
"""
import datetime

try:
    from backend.database import SessionLocal
    from backend.models import Match, MatchEvent, MatchStatistics, Team
    from backend.services.football_data_org import _request_get, BASE_URL
except ImportError:
    from database import SessionLocal
    from models import Match, MatchEvent, MatchStatistics, Team
    from services.football_data_org import _request_get, BASE_URL


WC_LEAGUE_ID = 2000


def fetch_match_detail(match_id: int):
    """Fetch full match detail from football-data.org /v4/matches/{id}."""
    resp = _request_get(f"{BASE_URL}/matches/{match_id}")
    if resp.status_code == 200:
        return resp.json()
    print(f"  ⚠️ Failed to fetch match {match_id}: {resp.status_code}")
    return None


def seed_match_details():
    db = SessionLocal()
    try:
        # Get finished WC matches
        finished = (
            db.query(Match)
            .filter(Match.league_id == WC_LEAGUE_ID, Match.status.in_(["FT", "AET", "PEN"]))
            .order_by(Match.start_time.asc())
            .all()
        )
        print(f"Found {len(finished)} finished WC matches\n")

        events_added = 0
        stats_added = 0

        for match in finished:
            # Skip if already has events
            existing_events = db.query(MatchEvent).filter(MatchEvent.match_id == match.id).count()
            if existing_events > 0:
                continue

            detail = fetch_match_detail(match.id)
            if not detail:
                continue

            home_name = detail.get("homeTeam", {}).get("name", "")
            away_name = detail.get("awayTeam", {}).get("name", "")
            print(f"  {home_name} vs {away_name} (id={match.id})")

            # Goals → MatchEvent
            for goal in detail.get("goals", []):
                scorer = goal.get("scorer", {})
                assist = goal.get("assist")
                team = goal.get("team", {})
                db.add(MatchEvent(
                    match_id=match.id,
                    minute=goal.get("minute"),
                    event_type="Goal",
                    team_id=team.get("id"),
                    player_name=scorer.get("name"),
                    player_id=scorer.get("id"),
                    detail=goal.get("type", "Regular"),
                    assist_player_name=assist.get("name") if assist else None,
                    assist_player_id=assist.get("id") if assist else None,
                ))
                events_added += 1

            # Bookings → MatchEvent
            for booking in detail.get("bookings", []):
                player = booking.get("player", {})
                team = booking.get("team", {})
                db.add(MatchEvent(
                    match_id=match.id,
                    minute=booking.get("minute"),
                    event_type="Card",
                    team_id=team.get("id"),
                    player_name=player.get("name"),
                    player_id=player.get("id"),
                    detail=booking.get("card", "YELLOW"),
                ))
                events_added += 1

            # Substitutions → MatchEvent
            for sub in detail.get("substitutions", []):
                team = sub.get("team", {})
                player_out = sub.get("playerOut", {})
                player_in = sub.get("playerIn", {})
                db.add(MatchEvent(
                    match_id=match.id,
                    minute=sub.get("minute"),
                    event_type="Subst",
                    team_id=team.get("id"),
                    player_name=player_out.get("name"),
                    player_id=player_out.get("id"),
                    detail=f"Out: {player_out.get('name')} → In: {player_in.get('name')}",
                    assist_player_name=player_in.get("name"),
                    assist_player_id=player_in.get("id"),
                ))
                events_added += 1

            # Statistics → MatchStatistics (if available and not already stored)
            home_stats = detail.get("homeTeam", {}).get("statistics")
            away_stats = detail.get("awayTeam", {}).get("statistics")
            if home_stats and away_stats:
                existing_stats = db.query(MatchStatistics).filter(MatchStatistics.match_id == match.id).first()
                if not existing_stats:
                    db.add(MatchStatistics(
                        match_id=match.id,
                        possession_home=home_stats.get("ball_possession", 0),
                        possession_away=away_stats.get("ball_possession", 0),
                        shots_on_home=home_stats.get("shots_on_goal", 0),
                        shots_on_away=away_stats.get("shots_on_goal", 0),
                        shots_off_home=home_stats.get("shots_off_goal", 0),
                        shots_off_away=away_stats.get("shots_off_goal", 0),
                        corners_home=home_stats.get("corner_kicks", 0),
                        corners_away=away_stats.get("corner_kicks", 0),
                        fouls_home=home_stats.get("fouls", 0),
                        fouls_away=away_stats.get("fouls", 0),
                    ))
                    stats_added += 1

            db.commit()

        print(f"\n✅ Done! Events added: {events_added}, Stats added: {stats_added}")

    except Exception as e:
        db.rollback()
        print(f"❌ Error: {e}")
        raise
    finally:
        db.close()


if __name__ == "__main__":
    seed_match_details()
