from fastapi import APIRouter, Depends, Query
from sqlalchemy.orm import Session
from typing import List, Optional

try:
    from backend.database import get_db
    from backend.models import Team, Player, League
except ImportError:
    from database import get_db
    from models import Team, Player, League

router = APIRouter(prefix="/api/v1/search", tags=["search"])


@router.get("/teams")
def search_teams(
    q: str = Query(..., min_length=1, description="Search query"),
    league_id: Optional[int] = Query(None, description="Filter by league ID"),
    db: Session = Depends(get_db)
):
    """
    Search for teams by name with optional league filter.
    Uses case-insensitive fuzzy matching.
    """
    query = db.query(Team).filter(Team.name.ilike(f"%{q}%"))
    
    if league_id:
        query = query.filter(Team.league_id == league_id)
    
    teams = query.limit(20).all()
    
    # Enrich with league information
    results = []
    for team in teams:
        league = db.query(League).filter(League.id == team.league_id).first()
        results.append({
            "id": team.id,
            "name": team.name,
            "logo_url": team.logo_url,
            "stadium": team.stadium,
            "league": {
                "id": league.id,
                "name": league.name,
                "country": league.country,
                "logo_url": league.logo_url
            } if league else None
        })
    
    return results


@router.get("/players")
def search_players(
    q: str = Query(..., min_length=1, description="Search query"),
    team_id: Optional[int] = Query(None, description="Filter by team ID"),
    position: Optional[str] = Query(None, description="Filter by position"),
    db: Session = Depends(get_db)
):
    """
    Search for players by name with optional filters.
    Uses case-insensitive fuzzy matching.
    """
    query = db.query(Player).filter(Player.name.ilike(f"%{q}%"))
    
    if team_id:
        query = query.filter(Player.team_id == team_id)
    
    if position:
        query = query.filter(Player.position.ilike(f"%{position}%"))
    
    players = query.limit(20).all()
    
    # Enrich with team information
    results = []
    for player in players:
        team = db.query(Team).filter(Team.id == player.team_id).first()
        results.append({
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
    
    return results


@router.get("/all")
def search_all(
    q: str = Query(..., min_length=1, description="Search query"),
    db: Session = Depends(get_db)
):
    """
    Combined search for both teams and players.
    Returns top 5 results from each category.
    """
    # Search teams
    teams_query = db.query(Team).filter(Team.name.ilike(f"%{q}%")).limit(5).all()
    teams_results = []
    for team in teams_query:
        league = db.query(League).filter(League.id == team.league_id).first()
        teams_results.append({
            "id": team.id,
            "name": team.name,
            "logo_url": team.logo_url,
            "stadium": team.stadium,
            "league": {
                "id": league.id,
                "name": league.name,
                "country": league.country,
                "logo_url": league.logo_url
            } if league else None
        })
    
    # Search players
    players_query = db.query(Player).filter(Player.name.ilike(f"%{q}%")).limit(5).all()
    players_results = []
    for player in players_query:
        team = db.query(Team).filter(Team.id == player.team_id).first()
        players_results.append({
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
    
    return {
        "teams": teams_results,
        "players": players_results
    }
