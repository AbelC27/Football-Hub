from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session
from typing import List

try:
    from backend.database import get_db
    from backend.models import Team, Player, User
    from backend.auth import get_current_user
    from backend.schemas import User as UserSchema
except ImportError:
    from database import get_db
    from models import Team, Player, User
    from auth import get_current_user
    from schemas import User as UserSchema
from pydantic import BaseModel

router = APIRouter(prefix="/api/v1", tags=["user"])

class TeamResponse(BaseModel):
    id: int
    name: str
    logo_url: str
    
    class Config:
        from_attributes = True

class PlayerResponse(BaseModel):
    id: int
    name: str
    position: str
    team_id: int
    
    class Config:
        from_attributes = True

class FavoritesUpdate(BaseModel):
    favorite_team_id: int | None = None
    favorite_player_id: int | None = None

@router.get("/teams", response_model=List[TeamResponse])
def get_teams(db: Session = Depends(get_db)):
    teams = db.query(Team).all()
    return teams

@router.get("/players", response_model=List[PlayerResponse])
def get_players(db: Session = Depends(get_db)):
    players = db.query(Player).all()
    return players

@router.put("/user/favorites", response_model=UserSchema)
def update_favorites(
    favorites: FavoritesUpdate,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db)
):
    current_user.favorite_team_id = favorites.favorite_team_id
    current_user.favorite_player_id = favorites.favorite_player_id
    db.commit()
    db.refresh(current_user)
    return current_user
