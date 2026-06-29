from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy.orm import Session
from sqlalchemy import or_
from typing import Any, Dict, List, Optional
import re
try:
    from backend.database import get_db
    from backend.models import Match, League, Team, Prediction, Player, MatchEvent, MatchStatistics, ProviderIdMap
    from backend.schemas import (
        Match as MatchSchema,
        MatchXGLiveResponse as MatchXGLiveResponseSchema,
        MatchXGPreMatchResponse as MatchXGPreMatchResponseSchema,
        Prediction as PredictionSchema,
        MatchExperience as MatchExperienceSchema,
        NextEventPredictionResponse as NextEventPredictionResponseSchema,
    )
    from backend.services import apisports as apisports_client
    from backend.services.apisports import ApisportsQuotaExceeded
    from backend.services import fpl as fpl_client
except ImportError:
    from database import get_db
    from models import Match, League, Team, Prediction, Player, MatchEvent, MatchStatistics, ProviderIdMap
    from schemas import (
        Match as MatchSchema,
        MatchXGLiveResponse as MatchXGLiveResponseSchema,
        MatchXGPreMatchResponse as MatchXGPreMatchResponseSchema,
        Prediction as PredictionSchema,
        MatchExperience as MatchExperienceSchema,
        NextEventPredictionResponse as NextEventPredictionResponseSchema,
    )
    from services import apisports as apisports_client
    from services.apisports import ApisportsQuotaExceeded
    from services import fpl as fpl_client
import datetime
import logging
from services.data_aggregator import data_aggregator
from services.thesportsdb_service import thesportsdb
from services.api_football_service import api_football
try:
    from backend.ai.next_event_ranker import next_event_inference_service
except ImportError:
    from ai.next_event_ranker import next_event_inference_service

try:
    from backend.ai.xg_model import xg_inference_service
except ImportError:
    from ai.xg_model import xg_inference_service

router = APIRouter(prefix="/api/v1", tags=["api"])

logger = logging.getLogger(__name__)

SUPPORTED_COMPETITION_LEAGUE_IDS = {
    39,   # Premier League (API-Football)
    140,  # La Liga (API-Football)
    78,   # Bundesliga (API-Football)
    135,  # Serie A (API-Football)
    61,   # Ligue 1 (API-Football)
    4480, # Champions League (TheSportsDB)
    2021, # Premier League (football-data.org)
    2014, # La Liga (football-data.org)
    2002, # Bundesliga (football-data.org)
    2019, # Serie A (football-data.org)
    2015, # Ligue 1 (football-data.org)
    2001, # Champions League (football-data.org)
    2000, # FIFA World Cup (football-data.org)
}

SUPPORTED_LEAGUE_NAME_TOKENS = (
    "premier league",
    "la liga",
    "bundesliga",
    "serie a",
    "ligue 1",
    "champions league",
    "world cup",
)

FINISHED_MATCH_STATUSES = {"FT", "AET", "PEN"}
IN_PLAY_MATCH_STATUSES = {"LIVE", "HT", "1H", "2H", "ET"}
ASSIST_PATTERN = re.compile(r"assist(?:ed)?\s*[:\-]?\s*([A-Za-z0-9 .'-]+)", re.IGNORECASE)


def _normalize_text(value):
    return value.strip().lower() if isinstance(value, str) else ""


def _is_supported_league(league):
    if not league:
        return False

    if league.id in SUPPORTED_COMPETITION_LEAGUE_IDS:
        return True

    league_name = _normalize_text(league.name)
    return any(token in league_name for token in SUPPORTED_LEAGUE_NAME_TOKENS)


def _normalize_event_type(raw_type):
    normalized = _normalize_text(raw_type)

    if "goal" in normalized:
        return "goal"
    if "assist" in normalized:
        return "assist"
    if "card" in normalized:
        return "card"
    if "subst" in normalized or "substit" in normalized:
        return "substitution"

    return "other"


def _extract_assist_name(detail):
    if not detail:
        return None

    match = ASSIST_PATTERN.search(detail)
    if match:
        return match.group(1).strip()

    return None


def _serialize_player(player):
    return {
        "id": player.id,
        "name": player.name,
        "position": player.position or "Unknown",
        "photo_url": player.photo_url,
    }


def _get_league_for_team(team, db: Session, league_cache):
    if not team or not team.league_id:
        return None

    if team.league_id not in league_cache:
        league_cache[team.league_id] = db.query(League).filter(League.id == team.league_id).first()

    return league_cache[team.league_id]


def _get_cached_team(team_id, db: Session, team_cache):
    if team_id not in team_cache:
        team_cache[team_id] = db.query(Team).filter(Team.id == team_id).first()

    return team_cache[team_id]


def _resolve_competition(home_league, away_league):
    if home_league and away_league and home_league.id == away_league.id:
        return home_league

    for league in [home_league, away_league]:
        if league and "champions league" in _normalize_text(league.name):
            return league

    for league in [home_league, away_league]:
        if _is_supported_league(league):
            return league

    return None


def _build_recent_form(team_id, current_match_id, db: Session, team_cache, league_cache):
    recent_matches = (
        db.query(Match)
        .filter(
            Match.id != current_match_id,
            Match.status.in_(list(FINISHED_MATCH_STATUSES)),
            or_(Match.home_team_id == team_id, Match.away_team_id == team_id),
        )
        .order_by(Match.start_time.desc())
        .limit(30)
        .all()
    )

    results = []

    for past_match in recent_matches:
        home_team = _get_cached_team(past_match.home_team_id, db, team_cache)
        away_team = _get_cached_team(past_match.away_team_id, db, team_cache)

        home_league = _get_league_for_team(home_team, db, league_cache)
        away_league = _get_league_for_team(away_team, db, league_cache)

        if not (_is_supported_league(home_league) or _is_supported_league(away_league)):
            continue

        is_home = past_match.home_team_id == team_id
        opponent_team = away_team if is_home else home_team

        team_score = past_match.home_score if is_home else past_match.away_score
        opponent_score = past_match.away_score if is_home else past_match.home_score

        result = None
        if team_score is not None and opponent_score is not None:
            if team_score > opponent_score:
                result = "W"
            elif team_score < opponent_score:
                result = "L"
            else:
                result = "D"

        competition = _resolve_competition(home_league, away_league)

        results.append(
            {
                "match_id": past_match.id,
                "start_time": past_match.start_time,
                "status": past_match.status,
                "opponent_name": opponent_team.name if opponent_team else "Unknown",
                "opponent_logo": opponent_team.logo_url if opponent_team else None,
                "is_home": is_home,
                "team_score": team_score,
                "opponent_score": opponent_score,
                "result": result,
                "competition_name": competition.name if competition else None,
            }
        )

        if len(results) == 5:
            break

    return results


def _to_int_or_none(value):
    if value is None or value == "":
        return None

    try:
        return int(float(value))
    except (TypeError, ValueError):
        return None


def _to_float_or_none(value):
    if value is None or value == "":
        return None

    try:
        return float(value)
    except (TypeError, ValueError):
        return None


def _clamp01(value):
    if value is None:
        return None

    return max(0.0, min(1.0, value))


def _parse_birth_date(value):
    if not value:
        return None

    if isinstance(value, datetime.datetime):
        return value.date()

    if isinstance(value, datetime.date):
        return value

    if isinstance(value, str):
        cleaned = value.strip()
        if not cleaned:
            return None

        try:
            return datetime.datetime.fromisoformat(cleaned.replace("Z", "+00:00")).date()
        except ValueError:
            pass

        for date_fmt in ("%Y-%m-%d", "%d/%m/%Y", "%Y/%m/%d"):
            try:
                return datetime.datetime.strptime(cleaned, date_fmt).date()
            except ValueError:
                continue

    return None


def _calculate_age(birth_value):
    birth_date = _parse_birth_date(birth_value)
    if not birth_date:
        return None

    today = datetime.date.today()
    return today.year - birth_date.year - ((today.month, today.day) < (birth_date.month, birth_date.day))


def _matches_player_name(event_player_name, player_name):
    event_name = _normalize_text(event_player_name)
    target_name = _normalize_text(player_name)

    if not event_name or not target_name:
        return False

    return event_name == target_name or event_name in target_name or target_name in event_name


def _build_player_performance_snapshot(player, db: Session, team_cache, league_cache):
    if not player or not player.team_id:
        return {
            "recent_form": [],
            "yellow_cards": None,
            "red_cards": None,
            "matches_considered": 0,
        }

    candidate_matches = (
        db.query(Match)
        .filter(
            Match.status.in_(list(FINISHED_MATCH_STATUSES)),
            or_(Match.home_team_id == player.team_id, Match.away_team_id == player.team_id),
        )
        .order_by(Match.start_time.desc())
        .limit(80)
        .all()
    )

    supported_matches = []
    for match in candidate_matches:
        home_team = _get_cached_team(match.home_team_id, db, team_cache)
        away_team = _get_cached_team(match.away_team_id, db, team_cache)
        home_league = _get_league_for_team(home_team, db, league_cache)
        away_league = _get_league_for_team(away_team, db, league_cache)

        if _is_supported_league(home_league) or _is_supported_league(away_league):
            supported_matches.append(match)

    if not supported_matches:
        return {
            "recent_form": [],
            "yellow_cards": None,
            "red_cards": None,
            "matches_considered": 0,
        }

    match_ids = [match.id for match in supported_matches]
    events_by_match = {match_id: [] for match_id in match_ids}

    event_rows = (
        db.query(MatchEvent)
        .filter(MatchEvent.match_id.in_(match_ids))
        .order_by(MatchEvent.minute.asc(), MatchEvent.id.asc())
        .all()
    )
    for event in event_rows:
        events_by_match.setdefault(event.match_id, []).append(event)

    yellow_cards = 0
    red_cards = 0
    recent_form = []

    for match in supported_matches:
        is_home = match.home_team_id == player.team_id
        home_team = _get_cached_team(match.home_team_id, db, team_cache)
        away_team = _get_cached_team(match.away_team_id, db, team_cache)
        opponent_team = away_team if is_home else home_team

        team_score = match.home_score if is_home else match.away_score
        opponent_score = match.away_score if is_home else match.home_score

        result = None
        if team_score is not None and opponent_score is not None:
            if team_score > opponent_score:
                result = "W"
            elif team_score < opponent_score:
                result = "L"
            else:
                result = "D"

        player_goals = 0
        player_assists = 0
        player_yellow = 0
        player_red = 0

        for event in events_by_match.get(match.id, []):
            if not _matches_player_name(event.player_name, player.name):
                continue

            event_kind = _normalize_event_type(event.event_type)
            detail_normalized = _normalize_text(event.detail)

            if event_kind == "goal":
                player_goals += 1
            elif event_kind == "assist":
                player_assists += 1
            elif event_kind == "card":
                if "red" in detail_normalized:
                    player_red += 1
                else:
                    player_yellow += 1

        yellow_cards += player_yellow
        red_cards += player_red

        if len(recent_form) < 5:
            recent_form.append(
                {
                    "match_id": match.id,
                    "start_time": match.start_time,
                    "result": result,
                    "opponent_name": opponent_team.name if opponent_team else "Unknown",
                    "opponent_logo": opponent_team.logo_url if opponent_team else None,
                    "goals": player_goals,
                    "assists": player_assists,
                    "yellow_cards": player_yellow,
                    "red_cards": player_red,
                }
            )

    return {
        "recent_form": recent_form,
        "yellow_cards": yellow_cards,
        "red_cards": red_cards,
        "matches_considered": len(supported_matches),
    }


def _build_normalized_player_stats(player, enriched_player, performance_snapshot):
    raw_stats = enriched_player.get("stats") if isinstance(enriched_player.get("stats"), dict) else {}

    goals = _to_int_or_none(raw_stats.get("goals"))
    if goals is None:
        goals = _to_int_or_none(player.goals_season)

    assists = _to_int_or_none(raw_stats.get("assists"))
    if assists is None:
        assists = _to_int_or_none(player.assists_season)

    rating = _to_float_or_none(raw_stats.get("rating"))
    if rating is None:
        rating = _to_float_or_none(player.rating_season)

    minutes = _to_int_or_none(raw_stats.get("minutes"))
    if minutes is None:
        minutes = _to_int_or_none(raw_stats.get("minutes_played"))
    if minutes is None:
        minutes = _to_int_or_none(player.minutes_played)

    yellow_cards = performance_snapshot.get("yellow_cards")
    red_cards = performance_snapshot.get("red_cards")

    goal_involvements = None
    if goals is not None or assists is not None:
        goal_involvements = (goals or 0) + (assists or 0)

    return {
        "goals": goals,
        "assists": assists,
        "rating": rating,
        "minutes": minutes,
        "yellow_cards": yellow_cards,
        "red_cards": red_cards,
        "goal_involvements": goal_involvements,
    }


def _build_overall_score(stats, recent_form):
    form_points = None
    form_matches = len(recent_form) if recent_form else 0
    if form_matches > 0:
        point_map = {"W": 3, "D": 1, "L": 0}
        form_points = sum(point_map.get(match.get("result"), 0) for match in recent_form)

    components = [
        {
            "key": "rating",
            "label": "Season Rating",
            "weight": 35.0,
            "raw_value": stats.get("rating"),
            "normalized_value": _clamp01((stats.get("rating") or 0) / 10.0) if stats.get("rating") is not None else None,
            "expression": "rating / 10",
        },
        {
            "key": "goals",
            "label": "Goal Output",
            "weight": 20.0,
            "raw_value": stats.get("goals"),
            "normalized_value": _clamp01((stats.get("goals") or 0) / 20.0) if stats.get("goals") is not None else None,
            "expression": "min(goals / 20, 1)",
        },
        {
            "key": "assists",
            "label": "Chance Creation",
            "weight": 15.0,
            "raw_value": stats.get("assists"),
            "normalized_value": _clamp01((stats.get("assists") or 0) / 12.0) if stats.get("assists") is not None else None,
            "expression": "min(assists / 12, 1)",
        },
        {
            "key": "minutes",
            "label": "Availability",
            "weight": 15.0,
            "raw_value": stats.get("minutes"),
            "normalized_value": _clamp01((stats.get("minutes") or 0) / 3000.0) if stats.get("minutes") is not None else None,
            "expression": "min(minutes / 3000, 1)",
        },
        {
            "key": "discipline",
            "label": "Discipline",
            "weight": 5.0,
            "raw_value": {
                "yellow_cards": stats.get("yellow_cards"),
                "red_cards": stats.get("red_cards"),
            },
            "normalized_value": _clamp01(
                1 - (((stats.get("yellow_cards") or 0) * 0.03) + ((stats.get("red_cards") or 0) * 0.12))
            )
            if stats.get("yellow_cards") is not None and stats.get("red_cards") is not None
            else None,
            "expression": "max(0, 1 - (yellow_cards*0.03 + red_cards*0.12))",
        },
        {
            "key": "form",
            "label": "Recent Form",
            "weight": 10.0,
            "raw_value": form_points,
            "normalized_value": _clamp01((form_points or 0) / (form_matches * 3.0)) if form_points is not None else None,
            "expression": "recent_form_points / (matches * 3)",
        },
    ]

    available_components = [component for component in components if component["normalized_value"] is not None]
    available_weight = sum(component["weight"] for component in available_components)

    score_value = 0.0
    if available_weight > 0:
        weighted_total = sum(component["normalized_value"] * component["weight"] for component in available_components)
        score_value = round((weighted_total / available_weight) * 100, 1)

    for component in components:
        component["available"] = component["normalized_value"] is not None
        if component["available"] and available_weight > 0:
            component["contribution"] = round(
                ((component["normalized_value"] * component["weight"]) / available_weight) * 100,
                1,
            )
        else:
            component["contribution"] = 0.0

    return {
        "value": score_value,
        "available_weight": available_weight,
        "formula": "Weighted normalized score: rating (35%), goals (20%), assists (15%), minutes (15%), discipline (5%), recent form (10%). Missing metrics are excluded and remaining weights are re-normalized to 100.",
        "components": components,
    }


def _build_player_data_sources(player, enriched_player, performance_snapshot):
    raw_stats = enriched_player.get("stats") if isinstance(enriched_player.get("stats"), dict) else {}
    has_external_stats = bool(raw_stats.get("team_name") or raw_stats.get("league_name"))

    has_db_stats = any(
        metric is not None
        for metric in [
            player.goals_season,
            player.assists_season,
            player.rating_season,
            player.minutes_played,
        ]
    )

    stats_source = "api_football" if has_external_stats else "database" if has_db_stats else "missing"

    photo_url = enriched_player.get("photo_url")
    if photo_url and player.photo_url and photo_url == player.photo_url:
        photo_source = "database"
    elif photo_url and enriched_player.get("description"):
        photo_source = "the_sports_db"
    elif photo_url:
        photo_source = "database"
    else:
        photo_source = "missing"

    form_source = "match_history" if performance_snapshot.get("recent_form") else "missing"
    discipline_source = "match_events" if performance_snapshot.get("matches_considered", 0) > 0 else "missing"

    return {
        "photo": photo_source,
        "stats": stats_source,
        "form": form_source,
        "discipline": discipline_source,
    }


def _build_player_fallback_notes(data_sources, performance_snapshot):
    notes = []

    if data_sources.get("stats") != "api_football":
        notes.append("Advanced API-Football metrics unavailable; using local stats fallback when present.")

    if data_sources.get("photo") == "missing":
        notes.append("Player photo is missing from the configured data providers.")

    if data_sources.get("form") == "missing":
        notes.append("Recent form could not be built from supported match history.")

    if performance_snapshot.get("matches_considered", 0) == 0:
        notes.append("Disciplinary stats are unavailable because no supported finished matches were found.")

    return notes


def _calculate_metric_delta(left_value, right_value, precision=2):
    left_number = _to_float_or_none(left_value)
    right_number = _to_float_or_none(right_value)

    if left_number is None or right_number is None:
        return None

    return round(left_number - right_number, precision)


POSITION_GROUP_ORDER = ["Goalkeeper", "Defender", "Midfielder", "Attacker", "Unknown"]
STARTER_TARGET_BY_POSITION = {
    "Goalkeeper": 1,
    "Defender": 4,
    "Midfielder": 3,
    "Attacker": 3,
    "Unknown": 2,
}


def _average_or_none(values, precision=2):
    valid_values = [value for value in values if value is not None]
    if not valid_values:
        return None

    return round(sum(valid_values) / len(valid_values), precision)


def _resolve_team_result(team_score, opponent_score):
    if team_score > opponent_score:
        return "W", 3

    if team_score < opponent_score:
        return "L", 0

    return "D", 1


def _resolve_position_group(position):
    normalized = _normalize_text(position)

    if "goalkeeper" in normalized or normalized == "gk" or "keeper" in normalized:
        return "Goalkeeper"
    if "defence" in normalized or "defender" in normalized or "back" in normalized:
        return "Defender"
    if "midfield" in normalized or "midfielder" in normalized:
        return "Midfielder"
    if (
        "attacker" in normalized
        or "forward" in normalized
        or "striker" in normalized
        or "winger" in normalized
    ):
        return "Attacker"

    return "Unknown"


def _build_player_quality_score(player):
    rating = _to_float_or_none(player.rating_season)
    goals = _to_int_or_none(player.goals_season)
    assists = _to_int_or_none(player.assists_season)
    minutes = _to_int_or_none(player.minutes_played)

    components = []

    if rating is not None:
        components.append((max(0.0, min(1.0, rating / 10.0)), 0.55))

    if goals is not None or assists is not None:
        goal_involvements = (goals or 0) + (assists or 0)
        components.append((max(0.0, min(1.0, goal_involvements / 18.0)), 0.25))

    if minutes is not None:
        components.append((max(0.0, min(1.0, minutes / 2500.0)), 0.20))

    if not components:
        return None

    available_weight = sum(weight for _, weight in components)
    weighted_score = sum(component_value * weight for component_value, weight in components)

    return round((weighted_score / available_weight) * 100, 1)


def _build_player_availability_score(player):
    minutes = _to_int_or_none(player.minutes_played)
    if minutes is None:
        return None

    # Approximate availability with minutes played up to a 10-match baseline.
    return round(max(0.0, min(1.0, minutes / 900.0)) * 100, 1)


def _build_supported_team_match_history(team_id, db: Session, team_cache, league_cache):
    candidate_matches = (
        db.query(Match)
        .filter(
            Match.status.in_(list(FINISHED_MATCH_STATUSES)),
            Match.home_score.isnot(None),
            Match.away_score.isnot(None),
            or_(Match.home_team_id == team_id, Match.away_team_id == team_id),
        )
        .order_by(Match.start_time.desc())
        .limit(120)
        .all()
    )

    history = []

    for match in candidate_matches:
        home_team = _get_cached_team(match.home_team_id, db, team_cache)
        away_team = _get_cached_team(match.away_team_id, db, team_cache)

        home_league = _get_league_for_team(home_team, db, league_cache)
        away_league = _get_league_for_team(away_team, db, league_cache)

        if not (_is_supported_league(home_league) or _is_supported_league(away_league)):
            continue

        is_home = match.home_team_id == team_id
        opponent_team = away_team if is_home else home_team

        team_score = match.home_score if is_home else match.away_score
        opponent_score = match.away_score if is_home else match.home_score
        result, points = _resolve_team_result(team_score, opponent_score)

        competition = _resolve_competition(home_league, away_league)

        history.append(
            {
                "match_id": match.id,
                "start_time": match.start_time,
                "opponent_name": opponent_team.name if opponent_team else "Unknown",
                "opponent_logo": opponent_team.logo_url if opponent_team else None,
                "is_home": is_home,
                "team_score": team_score,
                "opponent_score": opponent_score,
                "result": result,
                "points": points,
                "competition_name": competition.name if competition else None,
            }
        )

    return history


def _build_team_totals(match_history):
    wins = 0
    draws = 0
    losses = 0
    goals_scored = 0
    goals_conceded = 0
    clean_sheets = 0

    for row in match_history:
        goals_scored += row["team_score"]
        goals_conceded += row["opponent_score"]

        if row["opponent_score"] == 0:
            clean_sheets += 1

        if row["result"] == "W":
            wins += 1
        elif row["result"] == "D":
            draws += 1
        else:
            losses += 1

    matches_played = len(match_history)
    form_last_five = [row["result"] for row in reversed(match_history[:5])]

    return {
        "matches_played": matches_played,
        "wins": wins,
        "draws": draws,
        "losses": losses,
        "goals_scored": goals_scored,
        "goals_conceded": goals_conceded,
        "goal_difference": goals_scored - goals_conceded,
        "clean_sheets": clean_sheets,
        "win_rate": round((wins / matches_played) * 100, 1) if matches_played > 0 else 0.0,
        "average_goals_scored": round(goals_scored / matches_played, 2) if matches_played > 0 else 0.0,
        "average_goals_conceded": round(goals_conceded / matches_played, 2) if matches_played > 0 else 0.0,
        "form": form_last_five,
    }


def _build_form_window_summary(match_history, window_size):
    window_matches = match_history[:window_size]
    chronological = list(reversed(window_matches))

    points_total = 0
    goals_for = 0
    goals_against = 0
    wins = 0
    draws = 0
    losses = 0

    home_away_split = {
        "home": {
            "played": 0,
            "wins": 0,
            "draws": 0,
            "losses": 0,
            "points": 0,
            "goals_for": 0,
            "goals_against": 0,
        },
        "away": {
            "played": 0,
            "wins": 0,
            "draws": 0,
            "losses": 0,
            "points": 0,
            "goals_for": 0,
            "goals_against": 0,
        },
    }

    form_sequence = []
    points_trend = []

    cumulative_points = 0
    for index, row in enumerate(chronological, start=1):
        points_total += row["points"]
        goals_for += row["team_score"]
        goals_against += row["opponent_score"]

        if row["result"] == "W":
            wins += 1
        elif row["result"] == "D":
            draws += 1
        else:
            losses += 1

        split_key = "home" if row["is_home"] else "away"
        split = home_away_split[split_key]
        split["played"] += 1
        split["points"] += row["points"]
        split["goals_for"] += row["team_score"]
        split["goals_against"] += row["opponent_score"]

        if row["result"] == "W":
            split["wins"] += 1
        elif row["result"] == "D":
            split["draws"] += 1
        else:
            split["losses"] += 1

        cumulative_points += row["points"]
        form_sequence.append(
            {
                "match_id": row["match_id"],
                "start_time": row["start_time"],
                "opponent_name": row["opponent_name"],
                "opponent_logo": row["opponent_logo"],
                "is_home": row["is_home"],
                "result": row["result"],
                "points": row["points"],
                "goals_for": row["team_score"],
                "goals_against": row["opponent_score"],
                "competition_name": row["competition_name"],
                "cumulative_points": cumulative_points,
            }
        )

        points_trend.append(
            {
                "label": f"M{index}",
                "match_id": row["match_id"],
                "result": row["result"],
                "points": row["points"],
                "cumulative_points": cumulative_points,
            }
        )

    for split in home_away_split.values():
        split["goal_difference"] = split["goals_for"] - split["goals_against"]
        split["points_per_match"] = round(split["points"] / split["played"], 2) if split["played"] > 0 else 0.0

    matches_count = len(window_matches)

    return {
        "window": window_size,
        "matches_count": matches_count,
        "wins": wins,
        "draws": draws,
        "losses": losses,
        "points": points_total,
        "points_per_match": round(points_total / matches_count, 2) if matches_count > 0 else 0.0,
        "goals_for": goals_for,
        "goals_against": goals_against,
        "goal_difference": goals_for - goals_against,
        "form": [row["result"] for row in form_sequence],
        "form_sequence": form_sequence,
        "points_trend": points_trend,
        "result_distribution": {
            "W": wins,
            "D": draws,
            "L": losses,
        },
        "home_away_split": home_away_split,
    }


def _build_squad_depth_metrics(team_id, db: Session):
    players = (
        db.query(Player)
        .filter(Player.team_id == team_id)
        .order_by(Player.position.asc(), Player.name.asc())
        .all()
    )

    position_groups: Dict[str, List[Dict[str, Any]]] = {key: [] for key in POSITION_GROUP_ORDER}

    for player in players:
        group = _resolve_position_group(player.position)
        quality_score = _build_player_quality_score(player)
        availability_score = _build_player_availability_score(player)

        position_groups[group].append(
            {
                "id": player.id,
                "name": player.name,
                "position": player.position or "Unknown",
                "minutes": _to_int_or_none(player.minutes_played),
                "quality_score": quality_score,
                "availability_score": availability_score,
            }
        )

    position_payload = []
    starter_quality_values = []
    bench_quality_values = []
    availability_values = []
    quality_data_points = 0
    availability_data_points = 0

    for position_key in POSITION_GROUP_ORDER:
        entries = position_groups[position_key]

        sorted_entries = sorted(
            entries,
            key=lambda entry: (
                entry["quality_score"] is not None,
                entry["quality_score"] or 0,
                entry["minutes"] or 0,
                entry["name"],
            ),
            reverse=True,
        )

        starter_target = min(STARTER_TARGET_BY_POSITION[position_key], len(sorted_entries))
        starters = sorted_entries[:starter_target]
        bench = sorted_entries[starter_target:]

        starter_quality = _average_or_none([entry["quality_score"] for entry in starters], precision=1)
        bench_quality = _average_or_none([entry["quality_score"] for entry in bench], precision=1)
        availability_pct = _average_or_none([entry["availability_score"] for entry in sorted_entries], precision=1)

        position_quality_points = len([entry for entry in sorted_entries if entry["quality_score"] is not None])
        position_availability_points = len(
            [entry for entry in sorted_entries if entry["availability_score"] is not None]
        )

        quality_data_points += position_quality_points
        availability_data_points += position_availability_points

        if starter_quality is not None:
            starter_quality_values.append(starter_quality)

        if bench_quality is not None:
            bench_quality_values.append(bench_quality)

        if availability_pct is not None:
            availability_values.append(availability_pct)

        depth_delta = None
        if starter_quality is not None and bench_quality is not None:
            depth_delta = round(starter_quality - bench_quality, 1)

        position_payload.append(
            {
                "position_key": position_key.lower(),
                "position_label": position_key,
                "squad_count": len(sorted_entries),
                "starter_count": len(starters),
                "bench_count": len(bench),
                "starter_quality": starter_quality,
                "bench_quality": bench_quality,
                "depth_delta": depth_delta,
                "availability_pct": availability_pct,
                "quality_data_points": position_quality_points,
                "availability_data_points": position_availability_points,
            }
        )

    squad_size = len(players)
    quality_coverage_pct = round((quality_data_points / squad_size) * 100, 1) if squad_size > 0 else 0.0
    availability_coverage_pct = round((availability_data_points / squad_size) * 100, 1) if squad_size > 0 else 0.0

    fallback_notes = []
    if quality_data_points == 0:
        fallback_notes.append("Starter/bench quality uses rating-goals-minutes and is unavailable for this squad.")
    if availability_data_points == 0:
        fallback_notes.append("Availability is missing because minutes-played data is not available.")

    return {
        "position_groups": position_payload,
        "overall": {
            "squad_size": squad_size,
            "starter_quality": _average_or_none(starter_quality_values, precision=1),
            "bench_quality": _average_or_none(bench_quality_values, precision=1),
            "availability_pct": _average_or_none(availability_values, precision=1),
            "quality_coverage_pct": quality_coverage_pct,
            "availability_coverage_pct": availability_coverage_pct,
        },
        "fallback_notes": fallback_notes,
    }

@router.get("/leagues")
def get_leagues(db: Session = Depends(get_db)):
    """Get all available leagues"""
    leagues = db.query(League).all()
    return leagues

@router.get("/live-matches")
def get_live_matches(
    db: Session = Depends(get_db),
    league_id: Optional[int] = Query(None, description="Filter to a specific league id"),
    status: Optional[str] = Query(
        None,
        description=(
            "Filter by status group: 'live', 'upcoming', 'finished', or a comma-"
            "separated list of raw codes (e.g. 'FT,AET'). Default returns all."
        ),
    ),
    date_from: Optional[str] = Query(None, description="Inclusive lower bound, YYYY-MM-DD"),
    date_to: Optional[str] = Query(None, description="Inclusive upper bound, YYYY-MM-DD"),
    days_back: Optional[int] = Query(None, ge=0, description="Shortcut: include matches from N days ago"),
    days_forward: Optional[int] = Query(None, ge=0, description="Shortcut: include matches up to N days ahead"),
    limit: int = Query(30, ge=1, le=200, description="Page size, default 30, max 200"),
    offset: int = Query(0, ge=0, description="Number of rows to skip for pagination"),
    order: str = Query("asc", pattern="^(asc|desc)$", description="Sort by kickoff: asc or desc"),
):
    """
    Return matches for the configured leagues, paginated.

    Without a `status` filter, returns the entire dataset (paginated). The
    `status` argument accepts the friendly groups `live`, `upcoming`,
    `finished`, or a raw comma-separated list of status codes.

    Response shape:
        {
            "items": [Match, ...],
            "total": 1234,
            "limit": 30,
            "offset": 0,
            "has_more": true
        }
    """
    status_groups = {
        "live": ["LIVE", "HT", "ET", "P", "1H", "2H"],
        "upcoming": ["NS", "TBD", "PST", "SUSP"],
        "finished": ["FT", "AET", "PEN"],
    }
    all_known_statuses = ["LIVE", "HT", "ET", "P", "1H", "2H", "NS", "TBD", "PST", "SUSP", "FT", "AET", "PEN"]

    if status:
        normalized = status.strip().lower()
        if normalized in status_groups:
            wanted_statuses = status_groups[normalized]
        else:
            wanted_statuses = [s.strip().upper() for s in status.split(",") if s.strip()]
    else:
        wanted_statuses = all_known_statuses

    query = db.query(Match).filter(Match.status.in_(wanted_statuses))

    # Resolve the requested time window. No defaults: caller decides whether
    # to narrow by date. The pagination keeps the response cheap regardless.
    window_start = None
    window_end = None
    now_utc = datetime.datetime.utcnow()

    if days_back is not None:
        window_start = now_utc - datetime.timedelta(days=days_back)
    if days_forward is not None:
        window_end = now_utc + datetime.timedelta(days=days_forward)

    if date_from:
        try:
            window_start = datetime.datetime.strptime(date_from, "%Y-%m-%d")
        except ValueError as exc:
            raise HTTPException(status_code=400, detail=f"Invalid date_from: {exc}")
    if date_to:
        try:
            # Make date_to inclusive of the entire day.
            window_end = datetime.datetime.strptime(date_to, "%Y-%m-%d") + datetime.timedelta(days=1)
        except ValueError as exc:
            raise HTTPException(status_code=400, detail=f"Invalid date_to: {exc}")

    if window_start is not None:
        query = query.filter(Match.start_time >= window_start)
    if window_end is not None:
        query = query.filter(Match.start_time <= window_end)

    if league_id is not None:
        # Match either explicit league_id on Match or via home team membership.
        query = query.outerjoin(Team, Team.id == Match.home_team_id).filter(
            or_(Match.league_id == league_id, Team.league_id == league_id)
        )

    total = query.with_entities(Match.id).count()

    sort_column = Match.start_time.asc() if order == "asc" else Match.start_time.desc()
    matches = (
        query.order_by(sort_column, Match.id.asc())
        .offset(offset)
        .limit(limit)
        .all()
    )

    if not matches:
        return {
            "items": [],
            "total": total,
            "limit": limit,
            "offset": offset,
            "has_more": False,
        }

    # Bulk-fetch every team referenced by the matches in a single query
    # instead of doing 2 round-trips per match (N+1). With a remote Supabase
    # pooler this is the difference between sub-second and 30+ seconds.
    team_ids = set()
    for match in matches:
        if match.home_team_id is not None:
            team_ids.add(match.home_team_id)
        if match.away_team_id is not None:
            team_ids.add(match.away_team_id)

    teams_by_id = {
        team.id: team
        for team in db.query(Team).filter(Team.id.in_(team_ids)).all()
    } if team_ids else {}

    items = []
    for match in matches:
        home_team = teams_by_id.get(match.home_team_id)
        away_team = teams_by_id.get(match.away_team_id)

        items.append({
            "id": match.id,
            "start_time": match.start_time,
            "status": match.status,
            "home_score": match.home_score,
            "away_score": match.away_score,
            "home_team_id": match.home_team_id,
            "away_team_id": match.away_team_id,
            "home_team_name": home_team.name if home_team else f"Team {match.home_team_id}",
            "away_team_name": away_team.name if away_team else f"Team {match.away_team_id}",
            "home_team_logo": home_team.logo_url if home_team else None,
            "away_team_logo": away_team.logo_url if away_team else None,
            "league_id": match.league_id if match.league_id else (home_team.league_id if home_team else None),
            "prediction": match.prediction,
        })

    return {
        "items": items,
        "total": total,
        "limit": limit,
        "offset": offset,
        "has_more": offset + len(items) < total,
    }

@router.get("/match/{match_id}/details")
def get_match_details(match_id: int, db: Session = Depends(get_db)):
    match = db.query(Match).filter(Match.id == match_id).first()
    if not match:
        raise HTTPException(status_code=404, detail="Match not found")
    
    # Get team details
    home_team = db.query(Team).filter(Team.id == match.home_team_id).first()
    away_team = db.query(Team).filter(Team.id == match.away_team_id).first()
    
    # Get players for each team
    home_players = db.query(Player).filter(Player.team_id == match.home_team_id).limit(11).all()
    away_players = db.query(Player).filter(Player.team_id == match.away_team_id).limit(11).all()
    
    return {
        "id": match.id,
        "start_time": match.start_time,
        "status": match.status,
        "home_score": match.home_score,
        "away_score": match.away_score,
        "home_team_id": match.home_team_id,
        "away_team_id": match.away_team_id,
        "home_team_name": home_team.name if home_team else f"Team {match.home_team_id}",
        "away_team_name": away_team.name if away_team else f"Team {match.away_team_id}",
        "home_team_logo": home_team.logo_url if home_team else None,
        "away_team_logo": away_team.logo_url if away_team else None,
        "home_team_stadium": home_team.stadium if home_team else None,
        "home_players": [{"name": p.name, "position": p.position} for p in home_players],
        "away_players": [{"name": p.name, "position": p.position} for p in away_players],
        "prediction": match.prediction
    }


@router.get("/match/{match_id}/experience", response_model=MatchExperienceSchema)
def get_match_experience(match_id: int, db: Session = Depends(get_db)):
    match = db.query(Match).filter(Match.id == match_id).first()
    if not match:
        raise HTTPException(status_code=404, detail="Match not found")

    partial_failures = []
    team_cache = {}
    league_cache = {}

    home_team = _get_cached_team(match.home_team_id, db, team_cache)
    away_team = _get_cached_team(match.away_team_id, db, team_cache)

    if not home_team or not away_team:
        raise HTTPException(status_code=404, detail="Match teams not found")

    home_league = _get_league_for_team(home_team, db, league_cache)
    away_league = _get_league_for_team(away_team, db, league_cache)

    if not (_is_supported_league(home_league) or _is_supported_league(away_league)):
        raise HTTPException(
            status_code=403,
            detail="Match is outside the supported competition scope (Top 5 + UCL)",
        )

    competition = _resolve_competition(home_league, away_league)

    home_squad = []
    away_squad = []
    try:
        home_players = (
            db.query(Player)
            .filter(Player.team_id == match.home_team_id)
            .order_by(Player.position.asc(), Player.name.asc())
            .all()
        )
        away_players = (
            db.query(Player)
            .filter(Player.team_id == match.away_team_id)
            .order_by(Player.position.asc(), Player.name.asc())
            .all()
        )

        home_squad = [_serialize_player(player) for player in home_players]
        away_squad = [_serialize_player(player) for player in away_players]
    except Exception:
        partial_failures.append(
            {
                "section": "squads",
                "message": "Could not load full squads for both teams.",
            }
        )

    events = []
    substitutions = []
    try:
        event_rows = (
            db.query(MatchEvent)
            .filter(MatchEvent.match_id == match_id)
            .order_by(MatchEvent.minute.asc(), MatchEvent.id.asc())
            .all()
        )

        for event in event_rows:
            event_kind = _normalize_event_type(event.event_type)
            detail = event.detail or None
            assist_player = _extract_assist_name(detail)

            if event_kind in {"goal", "assist", "card"}:
                events.append(
                    {
                        "id": event.id,
                        "minute": event.minute,
                        "event_type": event_kind,
                        "team_id": event.team_id,
                        "player_name": event.player_name,
                        "assist_player": assist_player,
                        "card_type": detail if event_kind == "card" else None,
                        "detail": detail,
                    }
                )

            if event_kind == "substitution":
                substitutions.append(
                    {
                        "id": event.id,
                        "minute": event.minute,
                        "team_id": event.team_id,
                        "player_name": event.player_name,
                        "detail": detail,
                    }
                )
    except Exception:
        partial_failures.append(
            {
                "section": "events",
                "message": "Could not load timeline events for this match.",
            }
        )

    prediction_payload = None
    try:
        prediction = db.query(Prediction).filter(Prediction.match_id == match_id).first()
        if prediction:
            prediction_payload = {
                "id": prediction.id,
                "match_id": prediction.match_id,
                "home_win_prob": prediction.home_win_prob,
                "draw_prob": prediction.draw_prob,
                "away_win_prob": prediction.away_win_prob,
                "confidence_score": prediction.confidence_score,
            }
    except Exception:
        partial_failures.append(
            {
                "section": "prediction",
                "message": "Could not load AI prediction for this match.",
            }
        )

    home_last_five = []
    away_last_five = []
    try:
        home_last_five = _build_recent_form(match.home_team_id, match.id, db, team_cache, league_cache)
        away_last_five = _build_recent_form(match.away_team_id, match.id, db, team_cache, league_cache)
    except Exception:
        partial_failures.append(
            {
                "section": "form",
                "message": "Could not load recent form for one or both teams.",
            }
        )

    return {
        "header": {
            "match_id": match.id,
            "start_time": match.start_time,
            "status": match.status,
            "score": {
                "home": match.home_score,
                "away": match.away_score,
            },
            "current_minute": match.current_minute,
            "competition": {
                "id": competition.id,
                "name": competition.name,
                "country": competition.country,
                "logo_url": competition.logo_url,
            }
            if competition
            else None,
        },
        "teams": {
            "home": {
                "id": home_team.id,
                "name": home_team.name,
                "logo_url": home_team.logo_url,
                "stadium": home_team.stadium,
            },
            "away": {
                "id": away_team.id,
                "name": away_team.name,
                "logo_url": away_team.logo_url,
                "stadium": away_team.stadium,
            },
        },
        "prediction": prediction_payload,
        "events": events,
        "lineups": {
            "home_starting_xi": home_squad[:11],
            "away_starting_xi": away_squad[:11],
            "substitutions": substitutions,
            "source": "estimated_from_team_squads_and_substitution_events",
        },
        "form": {
            "home_last_five": home_last_five,
            "away_last_five": away_last_five,
        },
        "squads": {
            "home": home_squad,
            "away": away_squad,
        },
        "partial_failures": partial_failures,
    }

@router.get("/match/{match_id}/prediction", response_model=PredictionSchema)
def get_match_prediction(match_id: int, db: Session = Depends(get_db)):
    prediction = db.query(Prediction).filter(Prediction.match_id == match_id).first()
    if not prediction:
        raise HTTPException(status_code=404, detail="Prediction not found")
    return prediction


@router.get("/match/{match_id}/next-events/prediction", response_model=NextEventPredictionResponseSchema)
def get_match_next_events_prediction(
    match_id: int,
    minute: Optional[int] = Query(None, ge=1, le=130, description="Optional minute override for live inference context."),
    db: Session = Depends(get_db),
):
    match = db.query(Match).filter(Match.id == match_id).first()
    if not match:
        raise HTTPException(status_code=404, detail="Match not found")

    team_cache = {}
    league_cache = {}

    home_team = _get_cached_team(match.home_team_id, db, team_cache)
    away_team = _get_cached_team(match.away_team_id, db, team_cache)
    if not home_team or not away_team:
        raise HTTPException(status_code=404, detail="Match teams not found")

    home_league = _get_league_for_team(home_team, db, league_cache)
    away_league = _get_league_for_team(away_team, db, league_cache)

    if not (_is_supported_league(home_league) or _is_supported_league(away_league)):
        raise HTTPException(
            status_code=403,
            detail="Next-event predictions are limited to Top 5 leagues + UCL matches.",
        )

    payload = next_event_inference_service.predict_for_match(
        db=db,
        match=match,
        minute_override=minute,
        top_k=3,
    )

    global_limitations = list(payload.get("global_limitations", []))
    if _normalize_text(match.status) not in {_normalize_text(status) for status in IN_PLAY_MATCH_STATUSES}:
        global_limitations.append(
            "Match is not in-play; this is a baseline context projection from available pre-match/timeline data."
        )

    deduped = []
    for note in global_limitations:
        if note and note not in deduped:
            deduped.append(note)

    payload["global_limitations"] = deduped
    return payload


@router.get("/match/{match_id}/xg/pre-match", response_model=MatchXGPreMatchResponseSchema)
def get_match_xg_pre_match(
    match_id: int,
    db: Session = Depends(get_db),
):
    match = db.query(Match).filter(Match.id == match_id).first()
    if not match:
        raise HTTPException(status_code=404, detail="Match not found")

    team_cache = {}
    league_cache = {}

    home_team = _get_cached_team(match.home_team_id, db, team_cache)
    away_team = _get_cached_team(match.away_team_id, db, team_cache)
    if not home_team or not away_team:
        raise HTTPException(status_code=404, detail="Match teams not found")

    home_league = _get_league_for_team(home_team, db, league_cache)
    away_league = _get_league_for_team(away_team, db, league_cache)

    if not (_is_supported_league(home_league) or _is_supported_league(away_league)):
        raise HTTPException(
            status_code=403,
            detail="xG forecasts are limited to Top 5 leagues + UCL matches.",
        )

    return xg_inference_service.predict_pre_match(db=db, match=match)


@router.get("/match/{match_id}/xg/live", response_model=MatchXGLiveResponseSchema)
def get_match_xg_live(
    match_id: int,
    minute: Optional[int] = Query(None, ge=0, le=130, description="Optional minute override for live xG context."),
    db: Session = Depends(get_db),
):
    match = db.query(Match).filter(Match.id == match_id).first()
    if not match:
        raise HTTPException(status_code=404, detail="Match not found")

    team_cache = {}
    league_cache = {}

    home_team = _get_cached_team(match.home_team_id, db, team_cache)
    away_team = _get_cached_team(match.away_team_id, db, team_cache)
    if not home_team or not away_team:
        raise HTTPException(status_code=404, detail="Match teams not found")

    home_league = _get_league_for_team(home_team, db, league_cache)
    away_league = _get_league_for_team(away_team, db, league_cache)

    if not (_is_supported_league(home_league) or _is_supported_league(away_league)):
        raise HTTPException(
            status_code=403,
            detail="Live xG updates are limited to Top 5 leagues + UCL matches.",
        )

    payload = xg_inference_service.predict_live(db=db, match=match, minute_override=minute)

    if minute is None and _normalize_text(match.status) not in {_normalize_text(status) for status in IN_PLAY_MATCH_STATUSES}:
        payload_disclaimers = list(payload.get("disclaimers", []))
        payload_disclaimers.append(
            "Match is not in-play; live xG trend currently reflects baseline context and available historical/live feed state."
        )

        deduped = []
        for note in payload_disclaimers:
            if note and note not in deduped:
                deduped.append(note)

        payload["disclaimers"] = deduped

    return payload


def _wc_match_scorers(match, db: Session):
    """Return goal events for a WC match using tournament scorers data.

    Since free-tier APIs don't provide per-match goal detail for WC 2026,
    we identify which tournament scorers belong to the two teams in this match
    and return them as goal events. This gives the UI "who scores for each team"
    context on every match card.
    """
    try:
        from backend.services.football_data_org import fetch_competition_scorers
    except ImportError:
        from services.football_data_org import fetch_competition_scorers

    if match.status not in {"FT", "AET", "PEN"}:
        return []

    home_id = match.home_team_id
    away_id = match.away_team_id

    scorers = fetch_competition_scorers("WC")
    if not scorers:
        return []

    events = []
    event_id = match.id * 1000  # synthetic IDs

    for entry in scorers:
        team = entry.get("team", {})
        player = entry.get("player", {})
        team_id = team.get("id")

        if team_id not in (home_id, away_id):
            continue

        goals = entry.get("goals", 0) or 0
        assists = entry.get("assists", 0) or 0

        if goals > 0:
            event_id += 1
            events.append({
                "id": event_id,
                "minute": None,
                "event_type": "Goal",
                "team_id": team_id,
                "player_id": player.get("id"),
                "player_name": player.get("name"),
                "assist_player_id": None,
                "assist_player_name": None,
                "detail": f"{goals} goal{'s' if goals != 1 else ''} this tournament",
            })

        if assists > 0:
            event_id += 1
            events.append({
                "id": event_id,
                "minute": None,
                "event_type": "Assist",
                "team_id": team_id,
                "player_id": player.get("id"),
                "player_name": player.get("name"),
                "assist_player_id": None,
                "assist_player_name": None,
                "detail": f"{assists} assist{'s' if assists != 1 else ''} this tournament",
            })

    return events


@router.get("/match/{match_id}/events")
def get_match_events(match_id: int, db: Session = Depends(get_db)):
    """Return match events for ``match_id``.

    Behaviour (graceful chain — never throws on a degraded data path except
    when *both* providers fail in a recoverable way):

    1. Return cached ``MatchEvent`` rows if any exist.
    2. Only attempt enrichment for Premier League matches that have finished
       (FT/AET/PEN). Other cases return ``[]``.
    3. Try api-sports first (existing behaviour). Persists rows on success.
    4. If api-sports still leaves us with zero rows (mapping missing, network
       error, *or* ``ApisportsQuotaExceeded``), try the FPL fallback via
       ``services.fpl.persist_fpl_events_for_match``.
    5. Re-fetch events from DB and return them.
    6. ``503`` is only returned if api-sports raised quota *and* FPL also
       failed for a non-quota reason.

    Returns: a list of dicts with the keys ``id``, ``minute``, ``event_type``,
    ``team_id``, ``player_id``, ``player_name``, ``assist_player_id``,
    ``assist_player_name``, ``detail``.
    """
    PL_LOCAL_LEAGUE_ID = 2021
    PROVIDER = "apisports"

    match = db.query(Match).filter(Match.id == match_id).first()
    if match is None:
        raise HTTPException(status_code=404, detail="Match not found")

    def _serialize(events):
        return [
            {
                "id": e.id,
                "minute": e.minute,
                "event_type": e.event_type,
                "team_id": e.team_id,
                "player_id": e.player_id,
                "player_name": e.player_name,
                "assist_player_id": e.assist_player_id,
                "assist_player_name": e.assist_player_name,
                "detail": e.detail,
            }
            for e in events
        ]

    def _fetch_existing():
        return (
            db.query(MatchEvent)
            .filter(MatchEvent.match_id == match_id)
            .order_by(MatchEvent.minute.asc(), MatchEvent.id.asc())
            .all()
        )

    existing_events = _fetch_existing()
    if existing_events:
        return _serialize(existing_events)

    # Don't burn an api call on matches that haven't finished yet.
    if match.status not in {"FT", "AET", "PEN"}:
        return []

    # PL-only for live enrichment. WC uses tournament scorers as fallback.
    WC_LEAGUE_ID = 2000
    if match.league_id == WC_LEAGUE_ID:
        return _wc_match_scorers(match, db)

    if match.league_id != PL_LOCAL_LEAGUE_ID:
        return []

    apisports_quota_exceeded = False
    inserted_via_apisports = 0
    try:
        inserted_via_apisports = _try_apisports_for_match(db, match, PROVIDER)
    except ApisportsQuotaExceeded:
        db.rollback()
        apisports_quota_exceeded = True
        logger.warning(
            "api-sports quota exceeded while enriching match %d; will try FPL fallback.",
            match_id,
        )
    except Exception as exc:  # noqa: BLE001 - keep the chain alive
        db.rollback()
        logger.exception("api-sports enrichment failed for match %d: %s", match_id, exc)

    # If api-sports persisted rows, return them straight away.
    if inserted_via_apisports > 0:
        return _serialize(_fetch_existing())

    # ------------------------------------------------------------------
    # FPL fallback
    # ------------------------------------------------------------------
    fpl_inserted = 0
    fpl_failed = False
    try:
        fpl_inserted = fpl_client.persist_fpl_events_for_match(db, match)
    except Exception as exc:  # noqa: BLE001 - degraded path
        fpl_failed = True
        db.rollback()
        logger.exception("FPL fallback failed for match %d: %s", match_id, exc)

    if fpl_inserted > 0:
        return _serialize(_fetch_existing())

    # If api-sports tripped the quota AND FPL didn't bail us out (returned 0
    # or itself raised), surface a 503 so callers know it's a transient
    # provider issue rather than "no events".
    if apisports_quota_exceeded and (fpl_failed or fpl_inserted == 0):
        # FPL legitimately can return 0 (e.g. fixture not finished, no
        # mapping). Only 503 when the *quota* was the cause AND we have no
        # other source. We still return [] (with 503) so the UI handles it
        # the same way it did before.
        raise HTTPException(status_code=503, detail="Provider quota exceeded; try later.")

    return _serialize(_fetch_existing())


def _try_apisports_for_match(db: Session, match: Match, provider: str) -> int:
    """Attempt to enrich ``match`` with api-sports events.

    Returns the number of newly-inserted ``MatchEvent`` rows. Raises
    ``ApisportsQuotaExceeded`` to allow the caller to chain a fallback.
    Other exceptions propagate and the caller is responsible for rollback.
    """
    fixture_map_row = (
        db.query(ProviderIdMap)
        .filter(
            ProviderIdMap.provider == provider,
            ProviderIdMap.entity_type == "match",
            ProviderIdMap.local_id == match.id,
        )
        .first()
    )
    apisports_fixture_id = fixture_map_row.external_id if fixture_map_row else None

    team_map_rows = (
        db.query(ProviderIdMap)
        .filter(
            ProviderIdMap.provider == provider,
            ProviderIdMap.entity_type == "team",
            ProviderIdMap.local_id.in_([match.home_team_id, match.away_team_id]),
        )
        .all()
    )
    local_team_to_external = {row.local_id: row.external_id for row in team_map_rows}
    external_team_to_local = {row.external_id: row.local_id for row in team_map_rows}

    apisports_home = local_team_to_external.get(match.home_team_id)
    apisports_away = local_team_to_external.get(match.away_team_id)

    if apisports_fixture_id is None:
        if apisports_home is None or apisports_away is None:
            logger.warning(
                "Cannot resolve apisports fixture for match %d: missing team mapping "
                "(home=%s away=%s)",
                match.id,
                apisports_home,
                apisports_away,
            )
            return 0

        if not match.start_time:
            logger.warning("Match %d has no start_time; cannot resolve fixture by date.", match.id)
            return 0

        kickoff_date = match.start_time.date() if hasattr(match.start_time, "date") else match.start_time
        date_iso = kickoff_date.isoformat()
        season = apisports_client.current_pl_season()

        candidates = apisports_client.get_fixtures_by_date(
            season=season,
            date_iso=date_iso,
            team_apisports_id=apisports_home,
        )

        for candidate in candidates:
            teams_block = (candidate or {}).get("teams") or {}
            home_id = ((teams_block.get("home") or {}).get("id"))
            away_id = ((teams_block.get("away") or {}).get("id"))
            if home_id == apisports_home and away_id == apisports_away:
                fixture_block = (candidate or {}).get("fixture") or {}
                apisports_fixture_id = fixture_block.get("id")
                break

        if apisports_fixture_id is None:
            logger.warning(
                "No matching apisports fixture found for match %d on %s "
                "(home=%s away=%s).",
                match.id,
                date_iso,
                apisports_home,
                apisports_away,
            )
            return 0

        try:
            db.add(
                ProviderIdMap(
                    provider=provider,
                    entity_type="match",
                    local_id=match.id,
                    external_id=int(apisports_fixture_id),
                    confidence=100.0,
                    notes=f"resolved via fixtures-by-date {date_iso}",
                )
            )
            db.commit()
        except Exception as exc:  # noqa: BLE001
            db.rollback()
            logger.warning("Failed to persist match mapping for %d: %s", match.id, exc)

    events_payload = apisports_client.get_fixture_events(int(apisports_fixture_id))

    player_ids_needed = set()
    for ev in events_payload:
        player_block = (ev or {}).get("player") or {}
        assist_block = (ev or {}).get("assist") or {}
        if player_block.get("id"):
            player_ids_needed.add(int(player_block["id"]))
        if assist_block.get("id"):
            player_ids_needed.add(int(assist_block["id"]))

    player_map_rows = []
    if player_ids_needed:
        player_map_rows = (
            db.query(ProviderIdMap)
            .filter(
                ProviderIdMap.provider == provider,
                ProviderIdMap.entity_type == "player",
                ProviderIdMap.external_id.in_(list(player_ids_needed)),
            )
            .all()
        )
    external_player_to_local = {row.external_id: row.local_id for row in player_map_rows}

    inserted = 0
    for ev in events_payload:
        time_block = (ev or {}).get("time") or {}
        team_block = (ev or {}).get("team") or {}
        player_block = (ev or {}).get("player") or {}
        assist_block = (ev or {}).get("assist") or {}

        external_team_id = team_block.get("id")
        if external_team_id is None:
            continue
        local_team_id = external_team_to_local.get(int(external_team_id))
        if local_team_id is None:
            continue

        raw_type = (ev or {}).get("type") or ""
        normalized = raw_type.lower()
        if normalized == "goal":
            event_type = "Goal"
        elif normalized == "card":
            event_type = "Card"
        elif normalized == "subst":
            event_type = "Subst"
        else:
            event_type = raw_type or "Other"

        external_player_id = player_block.get("id")
        local_player_id = (
            external_player_to_local.get(int(external_player_id))
            if external_player_id is not None
            else None
        )

        external_assist_id = assist_block.get("id")
        local_assist_id = (
            external_player_to_local.get(int(external_assist_id))
            if external_assist_id is not None
            else None
        )

        db.add(
            MatchEvent(
                match_id=match.id,
                minute=time_block.get("elapsed"),
                event_type=event_type,
                team_id=local_team_id,
                player_name=player_block.get("name"),
                detail=(ev or {}).get("detail"),
                player_id=local_player_id,
                assist_player_id=local_assist_id,
                assist_player_name=assist_block.get("name"),
            )
        )
        inserted += 1

    db.commit()
    return inserted


@router.get("/match-events/bulk")
def get_match_events_bulk(
    match_ids: str = Query(..., description="Comma-separated list of match ids, e.g. '538149,538150'"),
    db: Session = Depends(get_db),
):
    """
    Bulk-fetch already-stored MatchEvent rows for a set of match ids.

    Designed for the homepage match cards: one DB query, no external calls.
    Matches without events come back as empty arrays. We deliberately do NOT
    hit api-sports/FPL here — the per-match `/match/{id}/events` endpoint
    handles lazy enrichment when the user opens a specific match.

    Response shape:
        {
            "<match_id>": [ {event}, {event}, ... ],
            "<match_id>": [],
            ...
        }
    """
    parsed_ids: List[int] = []
    for raw in (match_ids or "").split(","):
        raw = raw.strip()
        if not raw:
            continue
        try:
            parsed_ids.append(int(raw))
        except ValueError:
            raise HTTPException(status_code=400, detail=f"Invalid match id: {raw!r}")

    # De-duplicate and cap so a runaway client can't ask for the whole DB.
    unique_ids = list({mid for mid in parsed_ids})
    if not unique_ids:
        return {}
    if len(unique_ids) > 200:
        raise HTTPException(status_code=400, detail="Too many match_ids (max 200).")

    rows = (
        db.query(MatchEvent)
        .filter(MatchEvent.match_id.in_(unique_ids))
        .order_by(MatchEvent.match_id.asc(), MatchEvent.minute.asc().nullslast(), MatchEvent.id.asc())
        .all()
    )

    grouped: Dict[int, List[Dict[str, Any]]] = {mid: [] for mid in unique_ids}
    for row in rows:
        grouped.setdefault(row.match_id, []).append({
            "id": row.id,
            "minute": row.minute,
            "event_type": row.event_type,
            "team_id": row.team_id,
            "player_id": row.player_id,
            "player_name": row.player_name,
            "assist_player_id": row.assist_player_id,
            "assist_player_name": row.assist_player_name,
            "detail": row.detail,
        })

    # Stringify keys so the JSON response is predictable from the frontend.
    return {str(mid): grouped[mid] for mid in unique_ids}


@router.get("/match/{match_id}/statistics")
def get_match_statistics(match_id: int, db: Session = Depends(get_db)):
    """Get statistics for a match"""
    stats = db.query(MatchStatistics).filter(MatchStatistics.match_id == match_id).first()
    if not stats:
        raise HTTPException(status_code=404, detail="Statistics not found")
    return stats

@router.get("/league/{league_id}/standings")
def get_league_standings(league_id: int, db: Session = Depends(get_db)):
    """Compute standings from finished matches. Tournament-aware: returns grouped tables for WC."""

    # Detect tournament: check if any match for this league has group_name set
    is_tournament = (
        db.query(Match.id)
        .filter(Match.league_id == league_id, Match.group_name.isnot(None))
        .first()
    ) is not None

    if is_tournament:
        return _compute_tournament_standings(league_id, db)

    return _compute_league_standings(league_id, db)


def _compute_tournament_standings(league_id: int, db: Session):
    """Compute group-stage standings for a tournament (e.g. World Cup)."""
    from collections import defaultdict

    matches = (
        db.query(Match)
        .filter(
            Match.league_id == league_id,
            Match.stage == "GROUP_STAGE",
            Match.status.in_(list(FINISHED_MATCH_STATUSES)),
            Match.home_score.isnot(None),
            Match.away_score.isnot(None),
        )
        .order_by(Match.start_time.asc())
        .all()
    )

    # Also grab scheduled group matches to know which teams belong to which group
    all_group_matches = (
        db.query(Match)
        .filter(Match.league_id == league_id, Match.group_name.isnot(None))
        .all()
    )

    # Build team→group mapping from all group matches
    team_group: dict = {}
    for m in all_group_matches:
        if m.home_team_id and m.group_name:
            team_group[m.home_team_id] = m.group_name
        if m.away_team_id and m.group_name:
            team_group[m.away_team_id] = m.group_name

    # Stats per team
    stats: dict = defaultdict(lambda: {
        "played": 0, "won": 0, "drawn": 0, "lost": 0,
        "goals_for": 0, "goals_against": 0, "form": [],
    })

    for match in matches:
        h, a = match.home_team_id, match.away_team_id
        hg, ag = match.home_score, match.away_score

        stats[h]["played"] += 1
        stats[a]["played"] += 1
        stats[h]["goals_for"] += hg
        stats[h]["goals_against"] += ag
        stats[a]["goals_for"] += ag
        stats[a]["goals_against"] += hg

        if hg > ag:
            stats[h]["won"] += 1; stats[a]["lost"] += 1
            stats[h]["form"].append("W"); stats[a]["form"].append("L")
        elif hg < ag:
            stats[a]["won"] += 1; stats[h]["lost"] += 1
            stats[h]["form"].append("L"); stats[a]["form"].append("W")
        else:
            stats[h]["drawn"] += 1; stats[a]["drawn"] += 1
            stats[h]["form"].append("D"); stats[a]["form"].append("D")

    # Load team info
    all_team_ids = list(team_group.keys())
    teams_db = db.query(Team).filter(Team.id.in_(all_team_ids)).all() if all_team_ids else []
    team_map = {t.id: t for t in teams_db}

    # Build grouped output
    groups: dict = defaultdict(list)
    for team_id, group_name in team_group.items():
        s = stats[team_id]
        team = team_map.get(team_id)
        pts = s["won"] * 3 + s["drawn"]
        gd = s["goals_for"] - s["goals_against"]
        groups[group_name].append({
            "position": 0,
            "team_id": team_id,
            "team_name": team.name if team else f"Team {team_id}",
            "team_logo": team.logo_url if team else "",
            "played": s["played"],
            "won": s["won"],
            "drawn": s["drawn"],
            "lost": s["lost"],
            "goals_for": s["goals_for"],
            "goals_against": s["goals_against"],
            "goal_difference": gd,
            "points": pts,
            "form": "".join(s["form"][-3:]),
        })

    # Sort each group and assign positions
    result_groups = []
    for name in sorted(groups.keys()):
        table = groups[name]
        table.sort(key=lambda r: (-r["points"], -r["goal_difference"], -r["goals_for"], r["team_name"]))
        for idx, row in enumerate(table, 1):
            row["position"] = idx
        result_groups.append({"name": name, "table": table})

    return {"type": "tournament", "groups": result_groups}


def _compute_league_standings(league_id: int, db: Session):
    """Compute flat standings for a regular league."""
    teams = db.query(Team).filter(Team.league_id == league_id).all()
    if not teams:
        return []

    team_map = {team.id: team for team in teams}
    team_ids = list(team_map.keys())

    stats = {
        team_id: {
            "played": 0, "won": 0, "drawn": 0, "lost": 0,
            "goals_for": 0, "goals_against": 0, "form": [],
        }
        for team_id in team_ids
    }

    matches = (
        db.query(Match)
        .filter(
            Match.home_team_id.in_(team_ids),
            Match.away_team_id.in_(team_ids),
            Match.status == "FT",
            Match.home_score.isnot(None),
            Match.away_score.isnot(None),
        )
        .order_by(Match.start_time.asc())
        .all()
    )

    for match in matches:
        home_id = match.home_team_id
        away_id = match.away_team_id
        home_goals = match.home_score
        away_goals = match.away_score

        home_stats = stats[home_id]
        away_stats = stats[away_id]

        home_stats["played"] += 1
        away_stats["played"] += 1
        home_stats["goals_for"] += home_goals
        home_stats["goals_against"] += away_goals
        away_stats["goals_for"] += away_goals
        away_stats["goals_against"] += home_goals

        if home_goals > away_goals:
            home_stats["won"] += 1
            away_stats["lost"] += 1
            home_result, away_result = "W", "L"
        elif home_goals < away_goals:
            away_stats["won"] += 1
            home_stats["lost"] += 1
            home_result, away_result = "L", "W"
        else:
            home_stats["drawn"] += 1
            away_stats["drawn"] += 1
            home_result, away_result = "D", "D"

        home_stats["form"].append(home_result)
        away_stats["form"].append(away_result)

        if len(home_stats["form"]) > 5:
            home_stats["form"] = home_stats["form"][-5:]
        if len(away_stats["form"]) > 5:
            away_stats["form"] = away_stats["form"][-5:]

    standings = []
    for team_id in team_ids:
        team_stats = stats[team_id]
        team = team_map[team_id]

        points = team_stats["won"] * 3 + team_stats["drawn"]
        goal_difference = team_stats["goals_for"] - team_stats["goals_against"]

        standings.append(
            {
                "rank": 0,
                "team_id": team_id,
                "team_name": team.name,
                "team_logo": team.logo_url,
                "points": points,
                "played": team_stats["played"],
                "won": team_stats["won"],
                "drawn": team_stats["drawn"],
                "lost": team_stats["lost"],
                "goals_for": team_stats["goals_for"],
                "goals_against": team_stats["goals_against"],
                "goal_difference": goal_difference,
                "form": "".join(team_stats["form"]),
            }
        )

    standings.sort(
        key=lambda row: (
            -row["points"],
            -row["goal_difference"],
            -row["goals_for"],
            row["team_name"],
        )
    )

    for idx, row in enumerate(standings, start=1):
        row["rank"] = idx

    return standings


@router.get("/league/{league_id}/bracket")
def get_league_bracket(league_id: int, db: Session = Depends(get_db)):
    """Return knockout bracket for a tournament league (e.g. World Cup)."""

    ROUND_ORDER = [
        ("LAST_32", "Round of 32"),
        ("LAST_16", "Round of 16"),
        ("QUARTER_FINALS", "Quarter-Finals"),
        ("SEMI_FINALS", "Semi-Finals"),
        ("THIRD_PLACE", "Third Place"),
        ("FINAL", "Final"),
    ]

    knockout_matches = (
        db.query(Match)
        .filter(
            Match.league_id == league_id,
            Match.stage.isnot(None),
            Match.stage != "GROUP_STAGE",
        )
        .order_by(Match.start_time.asc())
        .all()
    )

    if not knockout_matches:
        return {"rounds": []}

    # Load teams for these matches
    team_ids = set()
    for m in knockout_matches:
        if m.home_team_id:
            team_ids.add(m.home_team_id)
        if m.away_team_id:
            team_ids.add(m.away_team_id)

    teams_db = db.query(Team).filter(Team.id.in_(list(team_ids))).all() if team_ids else []
    team_map = {t.id: t for t in teams_db}

    def _team_obj(team_id):
        if not team_id:
            return None
        t = team_map.get(team_id)
        if not t:
            return {"id": team_id, "name": "TBD", "logo": ""}
        return {"id": t.id, "name": t.name, "logo": t.logo_url or ""}

    # Group by stage
    by_stage: dict = {}
    for m in knockout_matches:
        by_stage.setdefault(m.stage, []).append(m)

    rounds = []
    for stage_key, display_name in ROUND_ORDER:
        matches_in_round = by_stage.get(stage_key, [])
        if not matches_in_round:
            continue
        rounds.append({
            "name": display_name,
            "stage": stage_key,
            "matches": [
                {
                    "id": m.id,
                    "home_team": _team_obj(m.home_team_id),
                    "away_team": _team_obj(m.away_team_id),
                    "home_score": m.home_score,
                    "away_score": m.away_score,
                    "status": m.status,
                    "start_time": m.start_time.isoformat() if m.start_time else None,
                }
                for m in matches_in_round
            ],
        })

    return {"rounds": rounds}


# Mapping from football-data.org league IDs to competition codes (for scorers API)
_LEAGUE_ID_TO_FD_CODE = {
    2021: "PL", 2014: "PD", 2002: "BL1", 2019: "SA", 2015: "FL1",
    2001: "CL", 2000: "WC",
}


@router.get("/league/{league_id}/scorers")
def get_league_scorers(league_id: int):
    """Return top scorers for a competition via football-data.org."""
    try:
        from backend.services.football_data_org import fetch_competition_scorers
    except ImportError:
        from services.football_data_org import fetch_competition_scorers

    code = _LEAGUE_ID_TO_FD_CODE.get(league_id)
    if not code:
        raise HTTPException(status_code=404, detail="Competition not supported for scorers")

    raw = fetch_competition_scorers(code)
    if not raw:
        return []

    scorers = []
    for entry in raw:
        player = entry.get("player", {})
        team = entry.get("team", {})
        scorers.append({
            "player_name": player.get("name"),
            "player_id": player.get("id"),
            "team_name": team.get("name"),
            "team_id": team.get("id"),
            "team_logo": team.get("crest", ""),
            "goals": entry.get("goals", 0),
            "assists": entry.get("assists", 0),
            "penalties": entry.get("penalties", 0),
        })

    return scorers


@router.get("/teams")
def get_teams(
    league_id: int = Query(None, description="Filter by league ID"),
    search: str = Query(None, description="Search team name"),
    skip: int = Query(0, ge=0),
    limit: int = Query(100, ge=1, le=200),
    db: Session = Depends(get_db)
):
    """Get all teams with optional filtering"""
    query = db.query(Team)
    
    if league_id:
        query = query.filter(Team.league_id == league_id)
    
    if search:
        query = query.filter(Team.name.ilike(f"%{search}%"))
    
    teams = query.offset(skip).limit(limit).all()
    
    # Enrich with league data
    result = []
    for team in teams:
        league = db.query(League).filter(League.id == team.league_id).first()
        player_count = db.query(Player).filter(Player.team_id == team.id).count()
        
        result.append({
            "id": team.id,
            "name": team.name,
            "logo_url": team.logo_url,
            "stadium": team.stadium,
            "league": {
                "id": league.id,
                "name": league.name,
                "country": league.country,
                "logo_url": league.logo_url
            } if league else None,
            "player_count": player_count
        })
    
    return result

@router.get("/teams/{team_id}")
def get_team_details(team_id: int, db: Session = Depends(get_db)):
    """Get detailed team information with full squad"""
    team = db.query(Team).filter(Team.id == team_id).first()
    if not team:
        raise HTTPException(status_code=404, detail="Team not found")
    
    league = db.query(League).filter(League.id == team.league_id).first()
    players = db.query(Player).filter(Player.team_id == team_id).all()
    
    # Group players by position
    position_groups = {
        "Goalkeeper": [],
        "Defender": [],
        "Midfielder": [],
        "Attacker": [],
        "Unknown": []
    }
    
    for player in players:
        player_dict = {
            "id": player.id,
            "name": player.name,
            "position": player.position,
            "nationality": player.nationality,
            "height": player.height,
            "photo_url": player.photo_url,
        }
        
        # Map position to group
        pos = player.position or "Unknown"
        if "Goalkeeper" in pos or "GK" in pos:
            position_groups["Goalkeeper"].append(player_dict)
        elif "Defence" in pos or "Defender" in pos or "Back" in pos:
            position_groups["Defender"].append(player_dict)
        elif "Midfield" in pos or "Midfielder" in pos:
            position_groups["Midfielder"].append(player_dict)
        elif "Attacker" in pos or "Forward" in pos or "Striker" in pos or "Winger" in pos:
            position_groups["Attacker"].append(player_dict)
        else:
            position_groups["Unknown"].append(player_dict)
    
    return {
        "id": team.id,
        "name": team.name,
        "logo_url": team.logo_url,
        "stadium": team.stadium,
        "league": {
            "id": league.id,
            "name": league.name,
            "country": league.country,
            "logo_url": league.logo_url
        } if league else None,
        "squad": position_groups,
        "total_players": len(players)
    }

@router.get("/players")
def get_players(
    team_id: int = Query(None, description="Filter by team ID"),
    position: str = Query(None, description="Filter by position"),
    search: str = Query(None, description="Search player name"),
    supported_only: bool = Query(False, description="Restrict players to Top 5 leagues + UCL"),
    skip: int = Query(0, ge=0),
    limit: int = Query(50, ge=1, le=100),
    db: Session = Depends(get_db)
):
    """Get all players with optional filtering"""
    query = db.query(Player)

    if supported_only:
        league_name_filters = [League.name.ilike(f"%{token}%") for token in SUPPORTED_LEAGUE_NAME_TOKENS]
        query = (
            query.join(Team, Player.team_id == Team.id)
            .join(League, Team.league_id == League.id)
            .filter(
                or_(
                    League.id.in_(list(SUPPORTED_COMPETITION_LEAGUE_IDS)),
                    *league_name_filters,
                )
            )
            .distinct()
        )
    
    if team_id:
        query = query.filter(Player.team_id == team_id)
    
    if position:
        query = query.filter(Player.position.ilike(f"%{position}%"))
    
    if search:
        query = query.filter(Player.name.ilike(f"%{search}%"))
    
    players = query.offset(skip).limit(limit).all()
    
    # Enrich with team data
    result = []
    for player in players:
        team = db.query(Team).filter(Team.id == player.team_id).first()
        league = db.query(League).filter(League.id == team.league_id).first() if team else None
        
        result.append({
            "id": player.id,
            "name": player.name,
            "position": player.position,
            "nationality": player.nationality,
            "height": player.height,
            "photo_url": player.photo_url,
            "team": {
                "id": team.id,
                "name": team.name,
                "logo_url": team.logo_url,
                "league_id": team.league_id,
            } if team else None,
            "league": {
                "id": league.id,
                "name": league.name,
                "country": league.country,
                "logo_url": league.logo_url,
            } if league else None,
        })
    
    return result

@router.get("/players/{player_id}")
def get_player_details(player_id: int, db: Session = Depends(get_db)):
    """Get detailed player information"""
    player = db.query(Player).filter(Player.id == player_id).first()
    if not player:
        raise HTTPException(status_code=404, detail="Player not found")
    
    team = db.query(Team).filter(Team.id == player.team_id).first()
    league = db.query(League).filter(League.id == team.league_id).first() if team else None
    
    return {
        "id": player.id,
        "name": player.name,
        "position": player.position,
        "nationality": player.nationality,
        "height": player.height,
        "photo_url": player.photo_url,
        "team": {
            "id": team.id,
            "name": team.name,
            "logo_url": team.logo_url,
            "stadium": team.stadium
        } if team else None,
        "league": {
            "id": league.id,
            "name": league.name,
            "country": league.country
        } if league else None
    }

@router.get("/players/{player_id}/enhanced")
def get_player_enhanced(player_id: int, db: Session = Depends(get_db)):
    """Get player details enriched with external API data"""
    player = db.query(Player).filter(Player.id == player_id).first()
    if not player:
        raise HTTPException(status_code=404, detail="Player not found")

    # ------------------------------------------------------------------
    # Per-player card counts from MatchEvent (FPL-sourced rows).
    # ------------------------------------------------------------------
    card_rows = (
        db.query(MatchEvent)
        .filter(
            MatchEvent.player_id == player.id,
            MatchEvent.event_type == "Card",
        )
        .all()
    )
    yellow_cards_total = sum(
        1 for row in card_rows if (row.detail or "").lower().startswith("yellow")
    )
    red_cards_total = sum(
        1 for row in card_rows if (row.detail or "").lower().startswith("red")
    )

    # ------------------------------------------------------------------
    # Derived overall rating (1..99 like FIFA/EA FC) when we don't have
    # one from a paid source. The function lives in services/data_aggregator
    # under enrich_player_data; we compute it here so the card can show a
    # real, deterministic number.
    # ------------------------------------------------------------------
    derived_rating = _compute_overall_rating(
        db,
        player,
        yellow_cards=yellow_cards_total,
        red_cards=red_cards_total,
    )

    # Base data from DB
    player_dict = {
        "id": player.id,
        "name": player.name,
        "position": player.position,
        "nationality": player.nationality,
        "height": player.height,
        "team_id": player.team_id,
        # Include new DB fields if they exist (they might be null)
        "photo_url": player.photo_url,
        "date_of_birth": player.date_of_birth,
        "stats": {
            "goals": player.goals_season,
            "assists": player.assists_season,
            "rating": player.rating_season,
            "minutes": player.minutes_played,
            "yellow_cards": yellow_cards_total,
            "red_cards": red_cards_total,
            "overall_rating": derived_rating,
        }
    }

    # Enrich with external data
    # This will fetch from APIs if data is missing or if we want fresh data
    # For now, we just call the aggregator which handles the logic
    enriched = data_aggregator.enrich_player_data(player_dict)

    # Re-attach the card counts and overall rating in case the aggregator
    # overwrote ``stats``. They are deterministic local computations and
    # we always want them on the response.
    if isinstance(enriched.get("stats"), dict):
        enriched["stats"]["yellow_cards"] = yellow_cards_total
        enriched["stats"]["red_cards"] = red_cards_total
        enriched["stats"]["overall_rating"] = derived_rating
    else:
        enriched["stats"] = player_dict["stats"]

    # Get team info
    team = db.query(Team).filter(Team.id == player.team_id).first()
    enriched['team'] = {
        "id": team.id,
        "name": team.name,
        "logo_url": team.logo_url
    } if team else None

    return enriched


def _compute_overall_rating(
    db: Session,
    player: Player,
    *,
    yellow_cards: int = 0,
    red_cards: int = 0,
) -> int:
    """
    FIFA/EA FC-style overall rating in the 50..95 range, computed from
    FPL signals (ICT index + points-per-game + total points) when
    available, falling back to a goals/assists/minutes heuristic when
    the player isn't an FPL element (e.g. non-PL squad rows).

    The percentile rank is taken **within the player's position group**
    so a defender isn't punished for not scoring like a forward. We blend:

        50 + position_baseline_offset
        + 25 * ict_percentile
        +  8 * ppg_percentile
        +  4 * total_points_percentile
        -  card penalty

    Result is deterministic per (player, FPL snapshot) pair.
    """
    pos_group = _resolve_position_group(player)

    has_signals = (
        player.fpl_ict_index is not None
        or player.fpl_points_per_game is not None
        or player.fpl_total_points is not None
    )

    if has_signals:
        score = _compute_fpl_signal_rating(db, player, pos_group)
    else:
        score = _compute_heuristic_rating(player, pos_group)

    score -= (yellow_cards * 0.15) + (red_cards * 1.2)
    return max(50, min(95, int(round(score))))


# ---------------------------------------------------------------------------
# Position-group baselines and resolver
# ---------------------------------------------------------------------------

_POSITION_BASELINES = {
    "GK": 62.0,
    "DEF": 63.0,
    "MID": 64.0,
    "FWD": 64.0,
}


def _overall_rating_to_match_rating(overall: Optional[int]) -> Optional[float]:
    """
    Convert the 50..95 EA-FC overall to a 1..10 match-rating scale (the
    one api-sports' ``games.rating`` would normally use). We map the 50..95
    band to roughly 5.5..8.5 — a "10" is reserved for true man-of-the-match
    territory which we can't infer from a season-aggregate, so we cap at 8.5.

    Returns None if ``overall`` is None.
    """
    if overall is None:
        return None
    clamped = max(50, min(95, int(overall)))
    # Linear map: 50 -> 5.5, 95 -> 8.5.
    rating = 5.5 + (clamped - 50) * (3.0 / 45.0)
    return round(rating, 2)


def _resolve_position_group(player: Player) -> str:
    """Return one of GK/DEF/MID/FWD. Prefers the FPL element_type when set."""
    et = getattr(player, "fpl_element_type", None)
    if et == 1:
        return "GK"
    if et == 2:
        return "DEF"
    if et == 3:
        return "MID"
    if et == 4:
        return "FWD"

    pos = (player.position or "").lower()
    if "goalkeeper" in pos:
        return "GK"
    if "back" in pos or "defender" in pos or "defence" in pos:
        return "DEF"
    if "midfield" in pos:
        return "MID"
    if "wing" in pos or "forward" in pos or "striker" in pos or "attack" in pos:
        return "FWD"
    return "MID"  # safe default


# ---------------------------------------------------------------------------
# Position cohort cache + percentile helpers
# ---------------------------------------------------------------------------

_PERCENTILE_CACHE: Dict[str, Any] = {
    "built_at_monotonic": 0.0,
    "ict": {"GK": [], "DEF": [], "MID": [], "FWD": []},
    "ppg": {"GK": [], "DEF": [], "MID": [], "FWD": []},
    "total_points": {"GK": [], "DEF": [], "MID": [], "FWD": []},
}
_PERCENTILE_CACHE_TTL_SECONDS = 60 * 60  # 1 hour


def _ensure_percentile_cache(db: Session) -> None:
    """Rebuild the per-position sorted-value lists if the cache is stale."""
    import time as _time
    now = _time.monotonic()
    if (now - _PERCENTILE_CACHE["built_at_monotonic"]) <= _PERCENTILE_CACHE_TTL_SECONDS \
            and _PERCENTILE_CACHE["ict"]["FWD"]:  # also require non-empty data
        return

    rows = (
        db.query(
            Player.fpl_element_type,
            Player.position,
            Player.fpl_ict_index,
            Player.fpl_points_per_game,
            Player.fpl_total_points,
        )
        .filter(Player.fpl_element_type.isnot(None))
        .all()
    )

    buckets_ict: Dict[str, List[float]] = {"GK": [], "DEF": [], "MID": [], "FWD": []}
    buckets_ppg: Dict[str, List[float]] = {"GK": [], "DEF": [], "MID": [], "FWD": []}
    buckets_total: Dict[str, List[float]] = {"GK": [], "DEF": [], "MID": [], "FWD": []}

    for et, pos, ict, ppg, total in rows:
        # Build a shim so _resolve_position_group can use the same logic.
        class _Shim:
            pass
        shim = _Shim()
        shim.fpl_element_type = et
        shim.position = pos
        group = _resolve_position_group(shim)  # type: ignore[arg-type]

        if ict is not None:
            buckets_ict[group].append(float(ict))
        if ppg is not None:
            buckets_ppg[group].append(float(ppg))
        if total is not None:
            buckets_total[group].append(float(total))

    for group in ("GK", "DEF", "MID", "FWD"):
        buckets_ict[group].sort()
        buckets_ppg[group].sort()
        buckets_total[group].sort()

    _PERCENTILE_CACHE["built_at_monotonic"] = now
    _PERCENTILE_CACHE["ict"] = buckets_ict
    _PERCENTILE_CACHE["ppg"] = buckets_ppg
    _PERCENTILE_CACHE["total_points"] = buckets_total


def _percentile_rank(sorted_values: List[float], target: Optional[float]) -> float:
    """Return the percentile of ``target`` within ``sorted_values`` (0..1)."""
    if target is None or not sorted_values:
        return 0.0
    # Linear scan is fine — buckets hold at most ~150 PL players per group.
    below = 0
    for value in sorted_values:
        if value < target:
            below += 1
        else:
            break
    return below / len(sorted_values)


def _compute_fpl_signal_rating(db: Session, player: Player, pos_group: str) -> float:
    """Percentile-based rating using the FPL signal columns."""
    _ensure_percentile_cache(db)

    ict_pct = _percentile_rank(_PERCENTILE_CACHE["ict"][pos_group], player.fpl_ict_index)
    ppg_pct = _percentile_rank(_PERCENTILE_CACHE["ppg"][pos_group], player.fpl_points_per_game)
    total_pct = _percentile_rank(_PERCENTILE_CACHE["total_points"][pos_group], player.fpl_total_points)

    baseline = _POSITION_BASELINES[pos_group]
    return (
        baseline
        + 25.0 * ict_pct
        + 8.0 * ppg_pct
        + 4.0 * total_pct
    )


# ---------------------------------------------------------------------------
# Fallback heuristic when FPL signals are missing
# ---------------------------------------------------------------------------

_HEURISTIC_WEIGHTS = {
    "GK": (6.0, 3.0),
    "DEF": (4.5, 2.0),
    "MID": (2.2, 1.6),
    "FWD": (1.4, 1.4),
}


def _compute_heuristic_rating(player: Player, pos_group: str) -> float:
    """Fallback for non-PL players (no FPL signals): use raw counting stats."""
    weight_goals, weight_assists = _HEURISTIC_WEIGHTS[pos_group]
    baseline = _POSITION_BASELINES[pos_group] + 2.0  # nudge so heuristic rows aren't all stuck low

    goals = player.goals_season or 0
    assists = player.assists_season or 0
    minutes = player.minutes_played or 0

    minutes_bonus = min(minutes / 200.0, 12.0)
    goals_bonus = min(goals * weight_goals, 18.0)
    assists_bonus = min(assists * weight_assists, 10.0)

    return baseline + minutes_bonus + goals_bonus + assists_bonus

@router.get("/teams/{team_id}/statistics")
def get_team_statistics(team_id: int, db: Session = Depends(get_db)):
    """Get team analysis metrics for Top 5 leagues + UEFA Champions League teams."""
    team = db.query(Team).filter(Team.id == team_id).first()
    if not team:
        raise HTTPException(status_code=404, detail="Team not found")

    team_cache = {team_id: team}
    league_cache = {}
    team_league = _get_league_for_team(team, db, league_cache)

    if not _is_supported_league(team_league):
        raise HTTPException(
            status_code=403,
            detail="Team analysis is limited to Top 5 leagues + UCL teams.",
        )

    match_history = _build_supported_team_match_history(team_id, db, team_cache, league_cache)
    totals = _build_team_totals(match_history)
    last_five = _build_form_window_summary(match_history, 5)
    last_ten = _build_form_window_summary(match_history, 10)
    squad_depth = _build_squad_depth_metrics(team_id, db)

    fallback_notes = []
    if totals["matches_played"] == 0:
        fallback_notes.append("No supported finished matches are available yet for this team.")
    elif last_ten["matches_count"] < 10:
        fallback_notes.append("Last-10 form is partial because fewer than 10 supported matches were found.")

    fallback_notes.extend(squad_depth.get("fallback_notes", []))

    return {
        "team_id": team_id,
        "team_name": team.name,
        "scope": "Top 5 leagues + UEFA Champions League",
        "league": {
            "id": team_league.id if team_league else None,
            "name": team_league.name if team_league else None,
            "country": team_league.country if team_league else None,
        },
        "matches_played": totals["matches_played"],
        "wins": totals["wins"],
        "draws": totals["draws"],
        "losses": totals["losses"],
        "goals_scored": totals["goals_scored"],
        "goals_conceded": totals["goals_conceded"],
        "goal_difference": totals["goal_difference"],
        "clean_sheets": totals["clean_sheets"],
        "win_rate": totals["win_rate"],
        "form": totals["form"],
        "average_goals_scored": totals["average_goals_scored"],
        "average_goals_conceded": totals["average_goals_conceded"],
        "form_metrics": {
            "last_5": last_five,
            "last_10": last_ten,
        },
        "squad_depth": squad_depth,
        "data_completeness": {
            "has_last_5": last_five["matches_count"] >= 5,
            "has_last_10": last_ten["matches_count"] >= 10,
            "squad_quality_coverage_pct": squad_depth["overall"].get("quality_coverage_pct", 0.0),
            "squad_availability_coverage_pct": squad_depth["overall"].get("availability_coverage_pct", 0.0),
        },
        "fallback_notes": fallback_notes,
    }

@router.get("/teams/{team1_id}/vs/{team2_id}")
def get_head_to_head(team1_id: int, team2_id: int, db: Session = Depends(get_db)):
    """Get head-to-head statistics between two teams"""
    team1 = db.query(Team).filter(Team.id == team1_id).first()
    team2 = db.query(Team).filter(Team.id == team2_id).first()
    
    if not team1 or not team2:
        raise HTTPException(status_code=404, detail="Team not found")
    
    # Find all matches between these two teams
    h2h_matches = db.query(Match).filter(
        ((Match.home_team_id == team1_id) & (Match.away_team_id == team2_id)) |
        ((Match.home_team_id == team2_id) & (Match.away_team_id == team1_id))
    ).order_by(Match.start_time.desc()).all()
    
    # Calculate H2H stats
    team1_wins = 0
    team2_wins = 0
    draws = 0
    team1_goals = 0
    team2_goals = 0
    
    match_history = []
    
    for match in h2h_matches:
        if match.status != 'FT':
            continue
            
        is_team1_home = match.home_team_id == team1_id
        team1_score = match.home_score if is_team1_home else match.away_score
        team2_score = match.away_score if is_team1_home else match.home_score
        
        if team1_score is not None and team2_score is not None:
            team1_goals += team1_score
            team2_goals += team2_score
            
            if team1_score > team2_score:
                team1_wins += 1
                result = 'team1_win'
            elif team1_score < team2_score:
                team2_wins += 1
                result = 'team2_win'
            else:
                draws += 1
                result = 'draw'
            
            winner_id = None
            if match.home_score > match.away_score:
                winner_id = match.home_team_id
            elif match.away_score > match.home_score:
                winner_id = match.away_team_id

            match_history.append({
                "id": match.id,
                "date": match.start_time,
                "home_team": team1.name if is_team1_home else team2.name,
                "away_team": team2.name if is_team1_home else team1.name,
                "home_score": match.home_score,
                "away_score": match.away_score,
                "result": result,
                "winner_id": winner_id
            })
    
    total_matches = team1_wins + team2_wins + draws
    
    return {
        "team1": {
            "id": team1_id,
            "name": team1.name,
            "logo_url": team1.logo_url,
            "wins": team1_wins,
            "goals": team1_goals
        },
        "team2": {
            "id": team2_id,
            "name": team2.name,
            "logo_url": team2.logo_url,
            "wins": team2_wins,
            "goals": team2_goals
        },
        "draws": draws,
        "total_matches": total_matches,
        "match_history": match_history[:10]  # Last 10 matches
    }

@router.get("/players/{player1_id}/vs/{player2_id}")
def get_player_comparison(player1_id: int, player2_id: int, db: Session = Depends(get_db)):
    """Compare two players side by side with normalized season stats and transparent scoring."""
    player1 = db.query(Player).filter(Player.id == player1_id).first()
    player2 = db.query(Player).filter(Player.id == player2_id).first()

    if not player1 or not player2:
        raise HTTPException(status_code=404, detail="Player not found")

    team_cache = {}
    league_cache = {}

    team1 = _get_cached_team(player1.team_id, db, team_cache)
    team2 = _get_cached_team(player2.team_id, db, team_cache)

    if not team1 or not team2:
        raise HTTPException(status_code=404, detail="Could not resolve team for one or both players")

    league1 = _get_league_for_team(team1, db, league_cache)
    league2 = _get_league_for_team(team2, db, league_cache)

    if not _is_supported_league(league1) or not _is_supported_league(league2):
        raise HTTPException(
            status_code=403,
            detail="Player comparison is limited to Top 5 leagues + UCL players.",
        )

    player1_dict = {
        "id": player1.id,
        "name": player1.name,
        "position": player1.position,
        "nationality": player1.nationality,
        "height": player1.height,
        "team_id": player1.team_id,
        "photo_url": player1.photo_url,
        "date_of_birth": player1.date_of_birth,
        "stats": {
            "goals": player1.goals_season,
            "assists": player1.assists_season,
            "rating": player1.rating_season,
            "minutes": player1.minutes_played,
        },
    }

    player2_dict = {
        "id": player2.id,
        "name": player2.name,
        "position": player2.position,
        "nationality": player2.nationality,
        "height": player2.height,
        "team_id": player2.team_id,
        "photo_url": player2.photo_url,
        "date_of_birth": player2.date_of_birth,
        "stats": {
            "goals": player2.goals_season,
            "assists": player2.assists_season,
            "rating": player2.rating_season,
            "minutes": player2.minutes_played,
        },
    }

    enriched_p1 = data_aggregator.enrich_player_data(player1_dict)
    enriched_p2 = data_aggregator.enrich_player_data(player2_dict)

    enriched_p1["team"] = {
        "id": team1.id,
        "name": team1.name,
        "logo_url": team1.logo_url,
    }
    enriched_p2["team"] = {
        "id": team2.id,
        "name": team2.name,
        "logo_url": team2.logo_url,
    }

    enriched_p1["league"] = {
        "id": league1.id,
        "name": league1.name,
        "country": league1.country,
        "logo_url": league1.logo_url,
    } if league1 else None
    enriched_p2["league"] = {
        "id": league2.id,
        "name": league2.name,
        "country": league2.country,
        "logo_url": league2.logo_url,
    } if league2 else None

    performance_p1 = _build_player_performance_snapshot(player1, db, team_cache, league_cache)
    performance_p2 = _build_player_performance_snapshot(player2, db, team_cache, league_cache)

    stats_p1 = _build_normalized_player_stats(player1, enriched_p1, performance_p1)
    stats_p2 = _build_normalized_player_stats(player2, enriched_p2, performance_p2)

    score_p1 = _build_overall_score(stats_p1, performance_p1.get("recent_form", []))
    score_p2 = _build_overall_score(stats_p2, performance_p2.get("recent_form", []))

    sources_p1 = _build_player_data_sources(player1, enriched_p1, performance_p1)
    sources_p2 = _build_player_data_sources(player2, enriched_p2, performance_p2)

    fallback_notes_p1 = _build_player_fallback_notes(sources_p1, performance_p1)
    fallback_notes_p2 = _build_player_fallback_notes(sources_p2, performance_p2)

    enriched_p1["age"] = _calculate_age(enriched_p1.get("date_of_birth"))
    enriched_p2["age"] = _calculate_age(enriched_p2.get("date_of_birth"))

    enriched_p1["stats"] = stats_p1
    enriched_p2["stats"] = stats_p2

    # FIFA-style 50..95 overall rating, mirrors the value the player card
    # shows on /player/{id}. Card counts come from the existing performance
    # snapshot so the number stays consistent across views.
    rating_p1 = _compute_overall_rating(
        db,
        player1,
        yellow_cards=performance_p1.get("yellow_cards") or 0,
        red_cards=performance_p1.get("red_cards") or 0,
    )
    rating_p2 = _compute_overall_rating(
        db,
        player2,
        yellow_cards=performance_p2.get("yellow_cards") or 0,
        red_cards=performance_p2.get("red_cards") or 0,
    )
    enriched_p1["stats"]["overall_rating"] = rating_p1
    enriched_p2["stats"]["overall_rating"] = rating_p2

    # Fall back the season "rating" tile (1..10 match-rating scale, the one
    # api-sports normally fills) to a proxy derived from the overall_rating
    # whenever the upstream value is missing. Without this the card just
    # shows "N/A" forever on the free tier.
    if enriched_p1["stats"].get("rating") is None:
        enriched_p1["stats"]["rating"] = _overall_rating_to_match_rating(rating_p1)
    if enriched_p2["stats"].get("rating") is None:
        enriched_p2["stats"]["rating"] = _overall_rating_to_match_rating(rating_p2)

    enriched_p1["recent_form"] = performance_p1.get("recent_form", [])
    enriched_p2["recent_form"] = performance_p2.get("recent_form", [])

    enriched_p1["overall_score"] = score_p1
    enriched_p2["overall_score"] = score_p2

    enriched_p1["data_sources"] = sources_p1
    enriched_p2["data_sources"] = sources_p2

    enriched_p1["fallback_notes"] = fallback_notes_p1
    enriched_p2["fallback_notes"] = fallback_notes_p2

    score_winner_id = None
    if score_p1.get("value", 0) > score_p2.get("value", 0):
        score_winner_id = player1.id
    elif score_p2.get("value", 0) > score_p1.get("value", 0):
        score_winner_id = player2.id

    return {
        "player1": enriched_p1,
        "player2": enriched_p2,
        "comparison": {
            "metric_deltas": {
                "goals": _calculate_metric_delta(stats_p1.get("goals"), stats_p2.get("goals")),
                "assists": _calculate_metric_delta(stats_p1.get("assists"), stats_p2.get("assists")),
                "rating": _calculate_metric_delta(stats_p1.get("rating"), stats_p2.get("rating")),
                "minutes": _calculate_metric_delta(stats_p1.get("minutes"), stats_p2.get("minutes")),
                "goal_involvements": _calculate_metric_delta(
                    stats_p1.get("goal_involvements"),
                    stats_p2.get("goal_involvements"),
                ),
                "overall_rating": _calculate_metric_delta(
                    rating_p1,
                    rating_p2,
                ),
                "overall_score": _calculate_metric_delta(score_p1.get("value"), score_p2.get("value"), precision=1),
            },
            "score_winner_id": score_winner_id,
            "scope": "Top 5 leagues + UEFA Champions League",
            "fallback_active": bool(fallback_notes_p1 or fallback_notes_p2),
        },
        "score_formula": score_p1.get("formula"),
        "note": "Stats combine local DB data, API-Football enrichment, and supported match-event history when available.",
    }
