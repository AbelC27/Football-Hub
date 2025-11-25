from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session
from sqlalchemy import and_, or_
from typing import List
import sys
import os
sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

try:
    from backend.database import get_db
    from backend.models import Match, Team, League
except ImportError:
    from database import get_db
    from models import Match, Team, League

from pydantic import BaseModel
from typing import Optional

router = APIRouter(prefix="/api/v1", tags=["standings"])

class TeamStanding(BaseModel):
    position: int
    team_id: int
    team_name: str
    played: int
    won: int
    drawn: int
    lost: int
    goals_for: int
    goals_against: int
    goal_difference: int
    points: int
    form: str  # e.g. "WDLWW"
    
    class Config:
        from_attributes = True

@router.get("/league/{league_id}/standings", response_model=List[TeamStanding])
def get_league_standings(league_id: int, db: Session = Depends(get_db)):
    """Calculate and return league standings"""
    
    # Get all teams in the league
    teams = db.query(Team).filter(Team.league_id == league_id).all()
    
    standings = []
    
    for team in teams:
        # Get all matches for this team
        matches = db.query(Match).filter(
            and_(
                or_(Match.home_team_id == team.id, Match.away_team_id == team.id),
                Match.status == 'FT',
                Match.home_score.isnot(None)
            )
        ).order_by(Match.start_time.desc()).all()
        
        played = len(matches)
        if played == 0:
            continue
        
        won = 0
        drawn = 0
        lost = 0
        goals_for = 0
        goals_against = 0
        form_results = []
        
        for match in matches[:5]:  # Last 5 for form
            is_home = match.home_team_id == team.id
            team_score = match.home_score if is_home else match.away_score
            opp_score = match.away_score if is_home else match.home_score
            
            if team_score > opp_score:
                result = 'W'
                won += 1 if match in matches else 0
            elif team_score == opp_score:
                result = 'D'
                drawn += 1 if match in matches else 0
            else:
                result = 'L'
                lost += 1 if match in matches else 0
            
            form_results.insert(0, result)  # Insert at beginning for chronological order
        
        # Calculate full stats for all matches
        for match in matches:
            is_home = match.home_team_id == team.id
            team_score = match.home_score if is_home else match.away_score
            opp_score = match.away_score if is_home else match.home_score
            
            goals_for += team_score
            goals_against += opp_score
            
            if team_score > opp_score:
                if match not in matches[:5]:
                    won += 1
            elif team_score == opp_score:
                if match not in matches[:5]:
                    drawn += 1
            else:
                if match not in matches[:5]:
                    lost += 1
        
        points = won * 3 + drawn
        goal_difference = goals_for - goals_against
        form = ''.join(form_results)
        
        standings.append(TeamStanding(
            position=0,  # Will be calculated after sorting
            team_id=team.id,
            team_name=team.name,
            played=played,
           won=won,
            drawn=drawn,
            lost=lost,
            goals_for=goals_for,
            goals_against=goals_against,
            goal_difference=goal_difference,
            points=points,
            form=form
        ))
    
    # Sort by points (desc), then goal difference (desc), then goals for (desc)
    standings.sort(key=lambda x: (-x.points, -x.goal_difference, -x.goals_for))
    
    # Assign positions
    for i, standing in enumerate(standings):
        standing.position = i + 1
    
    return standings
