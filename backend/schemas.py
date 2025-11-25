from pydantic import BaseModel
from typing import List, Optional
from datetime import datetime

class PlayerBase(BaseModel):
    name: str
    position: str
    height: Optional[str] = None
    nationality: Optional[str] = None

class Player(PlayerBase):
    id: int
    team_id: int
    class Config:
        from_attributes = True

class TeamBase(BaseModel):
    name: str
    logo_url: Optional[str] = None
    stadium: Optional[str] = None

class Team(TeamBase):
    id: int
    league_id: int
    players: List[Player] = []
    class Config:
        from_attributes = True

class MatchBase(BaseModel):
    start_time: datetime
    status: str
    home_score: Optional[int] = None
    away_score: Optional[int] = None

class Match(MatchBase):
    id: int
    home_team_id: int
    away_team_id: int
    prediction: Optional['Prediction'] = None
    class Config:
        from_attributes = True

class PredictionBase(BaseModel):
    home_win_prob: float
    draw_prob: float
    away_win_prob: float
    confidence_score: float

class Prediction(PredictionBase):
    id: int
    match_id: int
    class Config:
        from_attributes = True

class MatchEvent(BaseModel):
    id: int
    match_id: int
    minute: int
    event_type: str
    team_id: int
    player_name: str
    detail: Optional[str] = None    
    class Config:
        from_attributes = True

class MatchStatistics(BaseModel):
    id: int
    match_id: int
    possession_home: Optional[int] = None
    possession_away: Optional[int] = None
    shots_on_home: Optional[int] = None
    shots_on_away: Optional[int] = None
    shots_off_home: Optional[int] = None
    shots_off_away: Optional[int] = None
    corners_home: Optional[int] = None
    corners_away: Optional[int] = None
    fouls_home: Optional[int] = None
    fouls_away: Optional[int] = None    
    class Config:
        from_attributes = True

class Standing(BaseModel):
    rank: int
    team_id: int
    team_name: str
    team_logo: Optional[str] = None
    points: int
    played: int
    won: int
    drawn: int
    lost: int
    goals_for: int
    goals_against: int
    goal_difference: int
    form: Optional[str] = None
    class Config:
        from_attributes = True

# Auth Schemas
class UserBase(BaseModel):
    email: str
    username: str

class UserCreate(UserBase):
    password: str

class UserLogin(BaseModel):
    username: str
    password: str

class User(UserBase):
    id: int
    favorite_team_id: Optional[int] = None
    favorite_player_id: Optional[int] = None
    
    class Config:
        from_attributes = True

class Token(BaseModel):
    access_token: str
    token_type: str
