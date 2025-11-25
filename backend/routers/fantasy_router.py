from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session
from sqlalchemy import func
from typing import List

try:
    from backend.database import get_db
    from backend.models import User, Team, FantasySelection, Match
    from backend.auth import get_current_user
except ImportError:
    from database import get_db
    from models import User, Team, FantasySelection, Match
    from auth import get_current_user
from pydantic import BaseModel

router = APIRouter(prefix="/api/v1/fantasy", tags=["fantasy"])

class TeamSelectionRequest(BaseModel):
    team_ids: List[int]

class FantasyTeamResponse(BaseModel):
    id: int
    name: str
    logo_url: str
    
    class Config:
        from_attributes = True

class LeaderboardEntry(BaseModel):
    username: str
    points: int
    teams: List[str]

@router.get("/my-teams", response_model=List[FantasyTeamResponse])
def get_my_teams(
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db)
):
    """Get the current user's selected fantasy teams"""
    selections = db.query(FantasySelection).filter(
        FantasySelection.user_id == current_user.id
    ).all()
    
    teams = [db.query(Team).filter(Team.id == sel.team_id).first() for sel in selections]
    return [t for t in teams if t is not None]

@router.post("/select-teams")
def select_teams(
    request: TeamSelectionRequest,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db)
):
    """Select 5 teams for the fantasy league"""
    if len(request.team_ids) != 5:
        raise HTTPException(status_code=400, detail="You must select exactly 5 teams")
    
    # Check if all teams exist
    teams = db.query(Team).filter(Team.id.in_(request.team_ids)).all()
    if len(teams) != 5:
        raise HTTPException(status_code=400, detail="Some teams do not exist")
    
    # Delete existing selections
    db.query(FantasySelection).filter(
        FantasySelection.user_id == current_user.id
    ).delete()
    
    # Create new selections
    for team_id in request.team_ids:
        selection = FantasySelection(
            user_id=current_user.id,
            team_id=team_id
        )
        db.add(selection)
    
    db.commit()
    return {"message": "Teams selected successfully"}

@router.get("/my-points")
def get_my_points(
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db)
):
    """Calculate points based on selected teams' performance"""
    selections = db.query(FantasySelection).filter(
        FantasySelection.user_id == current_user.id
    ).all()
    
    if not selections:
        return {"points": 0, "message": "No teams selected yet"}
    
    team_ids = [sel.team_id for sel in selections]
    total_points = 0
    
    # Calculate points: Win = 3, Draw = 1, Loss = 0
    for team_id in team_ids:
        # Home wins
        home_wins = db.query(Match).filter(
            Match.home_team_id == team_id,
            Match.status == 'FT',
            Match.home_score > Match.away_score
        ).count()
        
        # Away wins
        away_wins = db.query(Match).filter(
            Match.away_team_id == team_id,
            Match.status == 'FT',
            Match.away_score > Match.home_score
        ).count()
        
        # Home draws
        home_draws = db.query(Match).filter(
            Match.home_team_id == team_id,
            Match.status == 'FT',
            Match.home_score == Match.away_score
        ).count()
        
        # Away draws
        away_draws = db.query(Match).filter(
            Match.away_team_id == team_id,
            Match.status == 'FT',
            Match.away_score == Match.home_score
        ).count()
        
        total_points += (home_wins + away_wins) * 3 + (home_draws + away_draws) * 1
    
    return {"points": total_points}

@router.get("/leaderboard", response_model=List[LeaderboardEntry])
def get_leaderboard(db: Session = Depends(get_db)):
    """Get the fantasy league leaderboard"""
    # Get all users with selections
    users_with_selections = db.query(User).join(FantasySelection).distinct().all()
    
    leaderboard = []
    
    for user in users_with_selections:
        selections = db.query(FantasySelection).filter(
            FantasySelection.user_id == user.id
        ).all()
        
        team_ids = [sel.team_id for sel in selections]
        team_names = [db.query(Team).filter(Team.id == tid).first().name for tid in team_ids]
        
        total_points = 0
        for team_id in team_ids:
            home_wins = db.query(Match).filter(
                Match.home_team_id == team_id,
                Match.status == 'FT',
                Match.home_score > Match.away_score
            ).count()
            
            away_wins = db.query(Match).filter(
                Match.away_team_id == team_id,
                Match.status == 'FT',
                Match.away_score > Match.home_score
            ).count()
            
            home_draws = db.query(Match).filter(
                Match.home_team_id == team_id,
                Match.status == 'FT',
                Match.home_score == Match.away_score
            ).count()
            
            away_draws = db.query(Match).filter(
                Match.away_team_id == team_id,
                Match.status == 'FT',
                Match.away_score == Match.home_score
            ).count()
            
            total_points += (home_wins + away_wins) * 3 + (home_draws + away_draws) * 1
        
        leaderboard.append({
            "username": user.username,
            "points": total_points,
            "teams": team_names
        })
    
    # Sort by points descending
    leaderboard.sort(key=lambda x: x["points"], reverse=True)
    
    return leaderboard
