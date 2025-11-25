from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy.orm import Session
from typing import List
try:
    from backend.database import get_db
    from backend.models import Match, League, Team, Prediction, Player, MatchEvent, MatchStatistics
    from backend.schemas import Match as MatchSchema, Prediction as PredictionSchema
except ImportError:
    from database import get_db
    from models import Match, League, Team, Prediction, Player, MatchEvent, MatchStatistics
    from schemas import Match as MatchSchema, Prediction as PredictionSchema
import datetime

router = APIRouter(prefix="/api/v1", tags=["api"])

@router.get("/leagues")
def get_leagues(db: Session = Depends(get_db)):
    """Get all available leagues"""
    leagues = db.query(League).all()
    return leagues

@router.get("/live-matches")
def get_live_matches(db: Session = Depends(get_db)):
    matches = db.query(Match).filter(Match.status.in_(['LIVE', 'NS', 'FT'])).all()
    
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
    """Get standings for a league"""
    try:
        from backend.models import Standing
    except ImportError:
        from models import Standing
        
    standings = db.query(Standing).filter(Standing.league_id == league_id).order_by(Standing.rank).all()
    
    # Enrich with team data
    enriched_standings = []
    for standing in standings:
        team = db.query(Team).filter(Team.id == standing.team_id).first()
        
        standing_dict = {
            "rank": standing.rank,
            "team_id": standing.team_id,
            "team_name": team.name if team else f"Team {standing.team_id}",
            "team_logo": team.logo_url if team else None,
            "points": standing.points,
            "played": standing.played,
            "won": standing.won,
            "drawn": standing.drawn,
            "lost": standing.lost,
            "goals_for": standing.goals_for,
            "goals_against": standing.goals_against,
            "goal_difference": standing.goal_difference,
            "form": standing.form
        }
        enriched_standings.append(standing_dict)
        
    return enriched_standings

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
            
            match_history.append({
                "date": match.start_time,
                "home_team": team1.name if is_team1_home else team2.name,
                "away_team": team2.name if is_team1_home else team1.name,
                "home_score": match.home_score,
                "away_score": match.away_score,
                "result": result
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
    
    # Get team info for both players
    team1 = db.query(Team).filter(Team.id == player1.team_id).first()
    team2 = db.query(Team).filter(Team.id == player2.team_id).first()
    
    return {
        "player1": {
            "id": player1.id,
            "name": player1.name,
            "position": player1.position,
            "nationality": player1.nationality,
            "height": player1.height,
            "team": {
                "id": team1.id,
                "name": team1.name,
                "logo_url": team1.logo_url
            } if team1 else None
        },
        "player2": {
            "id": player2.id,
            "name": player2.name,
            "position": player2.position,
            "nationality": player2.nationality,
            "height": player2.height,
            "team": {
                "id": team2.id,
                "name": team2.name,
                "logo_url": team2.logo_url
            } if team2 else None
        },
        "note": "Detailed performance stats require additional data integration"
    }
