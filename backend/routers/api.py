from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy.orm import Session
from sqlalchemy import or_
from typing import List
import re
try:
    from backend.database import get_db
    from backend.models import Match, League, Team, Prediction, Player, MatchEvent, MatchStatistics
    from backend.schemas import Match as MatchSchema, Prediction as PredictionSchema, MatchExperience as MatchExperienceSchema
except ImportError:
    from database import get_db
    from models import Match, League, Team, Prediction, Player, MatchEvent, MatchStatistics
    from schemas import Match as MatchSchema, Prediction as PredictionSchema, MatchExperience as MatchExperienceSchema
import datetime
from services.data_aggregator import data_aggregator
from services.thesportsdb_service import thesportsdb
from services.api_football_service import api_football

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
    skip: int = Query(0, ge=0),
    limit: int = Query(50, ge=1, le=100),
    db: Session = Depends(get_db)
):
    """Get all players with optional filtering"""
    query = db.query(Player)
    
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
        
        result.append({
            "id": player.id,
            "name": player.name,
            "position": player.position,
            "nationality": player.nationality,
            "height": player.height,
            "team": {
                "id": team.id,
                "name": team.name,
                "logo_url": team.logo_url
            } if team else None
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
    """Get comprehensive team statistics"""
    team = db.query(Team).filter(Team.id == team_id).first()
    if not team:
        raise HTTPException(status_code=404, detail="Team not found")
    
    # Get all matches for this team
    home_matches = db.query(Match).filter(Match.home_team_id == team_id).all()
    away_matches = db.query(Match).filter(Match.away_team_id == team_id).all()
    all_matches = home_matches + away_matches
    
    # Calculate statistics
    total_matches = len([m for m in all_matches if m.status == 'FT'])
    wins = 0
    draws = 0
    losses = 0
    goals_scored = 0
    goals_conceded = 0
    clean_sheets = 0
    
    for match in all_matches:
        if match.status != 'FT':
            continue
            
        is_home = match.home_team_id == team_id
        team_score = match.home_score if is_home else match.away_score
        opp_score = match.away_score if is_home else match.home_score
        
        if team_score is not None and opp_score is not None:
            goals_scored += team_score
            goals_conceded += opp_score
            
            if opp_score == 0:
                clean_sheets += 1
            
            if team_score > opp_score:
                wins += 1
            elif team_score < opp_score:
                losses += 1
            else:
                draws += 1
    
    # Recent form (last 5 matches)
    recent_matches = sorted(
        [m for m in all_matches if m.status == 'FT'],
        key=lambda x: x.start_time,
        reverse=True
    )[:5]
    
    form = []
    for match in reversed(recent_matches):
        is_home = match.home_team_id == team_id
        team_score = match.home_score if is_home else match.away_score
        opp_score = match.away_score if is_home else match.home_score
        
        if team_score > opp_score:
            form.append('W')
        elif team_score < opp_score:
            form.append('L')
        else:
            form.append('D')
    
    return {
        "team_id": team_id,
        "team_name": team.name,
        "matches_played": total_matches,
        "wins": wins,
        "draws": draws,
        "losses": losses,
        "goals_scored": goals_scored,
        "goals_conceded": goals_conceded,
        "goal_difference": goals_scored - goals_conceded,
        "clean_sheets": clean_sheets,
        "win_rate": round((wins / total_matches * 100) if total_matches > 0 else 0, 1),
        "form": form,
        "average_goals_scored": round(goals_scored / total_matches, 2) if total_matches > 0 else 0,
        "average_goals_conceded": round(goals_conceded / total_matches, 2) if total_matches > 0 else 0
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
    """Compare two players side by side"""
    player1 = db.query(Player).filter(Player.id == player1_id).first()
    player2 = db.query(Player).filter(Player.id == player2_id).first()
    
    if not player1 or not player2:
        raise HTTPException(status_code=404, detail="Player not found")
    
    # Prepare base data for enrichment
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
            "minutes": player1.minutes_played
        }
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
            "minutes": player2.minutes_played
        }
    }

    # Enrich with external data
    enriched_p1 = data_aggregator.enrich_player_data(player1_dict)
    enriched_p2 = data_aggregator.enrich_player_data(player2_dict)
    
    # Get team info for both players
    team1 = db.query(Team).filter(Team.id == player1.team_id).first()
    team2 = db.query(Team).filter(Team.id == player2.team_id).first()
    
    enriched_p1['team'] = {
        "id": team1.id,
        "name": team1.name,
        "logo_url": team1.logo_url
    } if team1 else None

    enriched_p2['team'] = {
        "id": team2.id,
        "name": team2.name,
        "logo_url": team2.logo_url
    } if team2 else None
    
    return {
        "player1": enriched_p1,
        "player2": enriched_p2,
        "note": "Detailed performance stats provided by API-Football and TheSportsDB"
    }
