from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy.orm import Session
from sqlalchemy import or_
from typing import Any, Dict, List, Optional
import re
try:
    from backend.database import get_db
    from backend.models import Match, League, Team, Prediction, Player, MatchEvent, MatchStatistics
    from backend.schemas import (
        Match as MatchSchema,
        MatchXGLiveResponse as MatchXGLiveResponseSchema,
        MatchXGPreMatchResponse as MatchXGPreMatchResponseSchema,
        Prediction as PredictionSchema,
        MatchExperience as MatchExperienceSchema,
        NextEventPredictionResponse as NextEventPredictionResponseSchema,
    )
except ImportError:
    from database import get_db
    from models import Match, League, Team, Prediction, Player, MatchEvent, MatchStatistics
    from schemas import (
        Match as MatchSchema,
        MatchXGLiveResponse as MatchXGLiveResponseSchema,
        MatchXGPreMatchResponse as MatchXGPreMatchResponseSchema,
        Prediction as PredictionSchema,
        MatchExperience as MatchExperienceSchema,
        NextEventPredictionResponse as NextEventPredictionResponseSchema,
    )
import datetime
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
}

SUPPORTED_LEAGUE_NAME_TOKENS = (
    "premier league",
    "la liga",
    "bundesliga",
    "serie a",
    "ligue 1",
    "champions league",
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
def get_live_matches(db: Session = Depends(get_db)):
    now_utc = datetime.datetime.utcnow()
    window_start = now_utc - datetime.timedelta(days=7)
    window_end = now_utc + datetime.timedelta(days=14)

    statuses = ['LIVE', 'HT', 'ET', 'P', 'NS', 'TBD', 'PST', 'FT', 'AET', 'PEN']

    matches = (
        db.query(Match)
        .filter(Match.status.in_(statuses))
        .filter(Match.start_time >= window_start)
        .filter(Match.start_time <= window_end)
        .order_by(Match.start_time.asc())
        .all()
    )
    
    # Enrich matches with team data
    enriched_matches = []
    for match in matches:
        home_team = db.query(Team).filter(Team.id == match.home_team_id).first()
        away_team = db.query(Team).filter(Team.id == match.away_team_id).first()
        
        match_dict = {
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
            "league_id": home_team.league_id if home_team else None,
            "prediction": match.prediction
        }
        enriched_matches.append(match_dict)
    
    return enriched_matches

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

@router.get("/match/{match_id}/events")
def get_match_events(match_id: int, db: Session = Depends(get_db)):
    """Get all events for a match"""
    events = db.query(MatchEvent).filter(MatchEvent.match_id == match_id).order_by(MatchEvent.minute).all()
    return events

@router.get("/match/{match_id}/statistics")
def get_match_statistics(match_id: int, db: Session = Depends(get_db)):
    """Get statistics for a match"""
    stats = db.query(MatchStatistics).filter(MatchStatistics.match_id == match_id).first()
    if not stats:
        raise HTTPException(status_code=404, detail="Statistics not found")
    return stats

@router.get("/league/{league_id}/standings")
def get_league_standings(league_id: int, db: Session = Depends(get_db)):
    """Compute standings from finished league matches for fresher results."""
    teams = db.query(Team).filter(Team.league_id == league_id).all()
    if not teams:
        return []

    team_map = {team.id: team for team in teams}
    team_ids = list(team_map.keys())

    stats = {
        team_id: {
            "played": 0,
            "won": 0,
            "drawn": 0,
            "lost": 0,
            "goals_for": 0,
            "goals_against": 0,
            "form": []
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
            Match.away_score.isnot(None)
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
                "form": "".join(team_stats["form"])
            }
        )

    standings.sort(
        key=lambda row: (
            -row["points"],
            -row["goal_difference"],
            -row["goals_for"],
            row["team_name"]
        )
    )

    for idx, row in enumerate(standings, start=1):
        row["rank"] = idx

    return standings

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
            "height": player.height
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
            "minutes": player.minutes_played
        }
    }
    
    # Enrich with external data
    # This will fetch from APIs if data is missing or if we want fresh data
    # For now, we just call the aggregator which handles the logic
    enriched = data_aggregator.enrich_player_data(player_dict)
    
    # Get team info
    team = db.query(Team).filter(Team.id == player.team_id).first()
    enriched['team'] = {
        "id": team.id,
        "name": team.name,
        "logo_url": team.logo_url
    } if team else None
    
    return enriched

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
                "overall_score": _calculate_metric_delta(score_p1.get("value"), score_p2.get("value"), precision=1),
            },
            "score_winner_id": score_winner_id,
            "scope": "Top 5 leagues + UEFA Champions League",
            "fallback_active": bool(fallback_notes_p1 or fallback_notes_p2),
        },
        "score_formula": score_p1.get("formula"),
        "note": "Stats combine local DB data, API-Football enrichment, and supported match-event history when available.",
    }
