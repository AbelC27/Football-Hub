from sqlalchemy import Column, Integer, String, Boolean, ForeignKey, DateTime, Float
from sqlalchemy.orm import relationship
try:
    from backend.database import Base
except ImportError:
    from database import Base
import datetime

class League(Base):
    __tablename__ = "leagues"
    id = Column(Integer, primary_key=True, index=True)
    name = Column(String, index=True)
    country = Column(String)
    logo_url = Column(String)
    teams = relationship("Team", back_populates="league")

class Team(Base):
    __tablename__ = "teams"
    id = Column(Integer, primary_key=True, index=True)
    name = Column(String, index=True)
    logo_url = Column(String)
    stadium = Column(String)
    league_id = Column(Integer, ForeignKey("leagues.id"))
    league = relationship("League", back_populates="teams")
    players = relationship("Player", back_populates="team")

class Player(Base):
    __tablename__ = "players"
    id = Column(Integer, primary_key=True, index=True)
    name = Column(String, index=True)
    position = Column(String)
    team_id = Column(Integer, ForeignKey("teams.id"))
    height = Column(String)
    nationality = Column(String)
    team = relationship("Team", back_populates="players")

class Match(Base):
    __tablename__ = "matches"
    id = Column(Integer, primary_key=True, index=True)
    home_team_id = Column(Integer, ForeignKey("teams.id"))
    away_team_id = Column(Integer, ForeignKey("teams.id"))
    start_time = Column(DateTime)
    status = Column(String) # LIVE, FT, NS
    home_score = Column(Integer, nullable=True)
    away_score = Column(Integer, nullable=True)
    
    prediction = relationship("Prediction", back_populates="match", uselist=False)

class Prediction(Base):
    __tablename__ = "predictions"
    id = Column(Integer, primary_key=True, index=True)
    match_id = Column(Integer, ForeignKey("matches.id"))
    home_win_prob = Column(Float)
    draw_prob = Column(Float)
    away_win_prob = Column(Float)
    confidence_score = Column(Float)
    match = relationship("Match", back_populates="prediction")

class MatchEvent(Base):
    __tablename__ = "match_events"
    id = Column(Integer, primary_key=True, index=True)
    match_id = Column(Integer, ForeignKey("matches.id"))
    minute = Column(Integer)
    event_type = Column(String)  # 'Goal', 'Card', 'Subst'
    team_id = Column(Integer, ForeignKey("teams.id"))
    player_name = Column(String)
    detail = Column(String)  # 'Yellow Card', 'Penalty', etc.
    
class MatchStatistics(Base):
    __tablename__ = "match_statistics"
    id = Column(Integer, primary_key=True, index=True)
    match_id = Column(Integer, ForeignKey("matches.id"), unique=True)
    possession_home = Column(Integer)
    possession_away = Column(Integer)
    shots_on_home = Column(Integer)
    shots_on_away = Column(Integer)
    shots_off_home = Column(Integer)
    shots_off_away = Column(Integer)
    corners_home = Column(Integer)
    corners_away = Column(Integer)
    fouls_home = Column(Integer)
    fouls_away = Column(Integer)

class Standing(Base):
    __tablename__ = "standings"
    id = Column(Integer, primary_key=True, index=True)
    league_id = Column(Integer, ForeignKey("leagues.id"))
    team_id = Column(Integer, ForeignKey("teams.id"))
    rank = Column(Integer)
    points = Column(Integer)
    played = Column(Integer)
    won = Column(Integer)
    drawn = Column(Integer)
    lost = Column(Integer)
    goals_for = Column(Integer)
    goals_against = Column(Integer)
    goal_difference = Column(Integer)
    form = Column(String, nullable=True)
    
    team = relationship("Team")
    league = relationship("League")

class User(Base):
    __tablename__ = "users"
    id = Column(Integer, primary_key=True, index=True)
    email = Column(String, unique=True, index=True)
    username = Column(String, unique=True, index=True)
    hashed_password = Column(String)
    created_at = Column(DateTime, default=datetime.datetime.utcnow)
    
    # Profile
    favorite_team_id = Column(Integer, ForeignKey("teams.id"), nullable=True)
    favorite_player_id = Column(Integer, ForeignKey("players.id"), nullable=True)
    
    # Relationships
    favorite_team = relationship("Team")
    favorite_player = relationship("Player")

class FantasySelection(Base):
    __tablename__ = "fantasy_selections"
    id = Column(Integer, primary_key=True, index=True)
    user_id = Column(Integer, ForeignKey("users.id"))
    team_id = Column(Integer, ForeignKey("teams.id"))
    
    # Relationships
    user = relationship("User")
    team = relationship("Team")
