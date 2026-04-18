from sqlalchemy import (
    Column,
    Integer,
    String,
    Boolean,
    ForeignKey,
    DateTime,
    Float,
    Numeric,
    Date,
    UniqueConstraint,
)
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
    
    # Enhanced Data (Optional)
    photo_url = Column(String, nullable=True)
    date_of_birth = Column(DateTime, nullable=True)
    market_value = Column(String, nullable=True)
    jersey_number = Column(Integer, nullable=True)
    
    # Stats (from API-Football)
    goals_season = Column(Integer, nullable=True)
    assists_season = Column(Integer, nullable=True)
    rating_season = Column(Float, nullable=True)
    minutes_played = Column(Integer, nullable=True)

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


class FantasyPlayerSquad(Base):
    __tablename__ = "fantasy_player_squads"

    id = Column(Integer, primary_key=True, index=True)
    user_id = Column(Integer, ForeignKey("users.id"), unique=True, nullable=False, index=True)
    budget_cap = Column(Numeric(10, 2), nullable=False, default=100.00)
    budget_spent = Column(Numeric(10, 2), nullable=False, default=0.00)
    created_at = Column(DateTime, default=datetime.datetime.utcnow, nullable=False)
    updated_at = Column(
        DateTime,
        default=datetime.datetime.utcnow,
        onupdate=datetime.datetime.utcnow,
        nullable=False,
    )

    user = relationship("User")
    players = relationship(
        "FantasySquadPlayer",
        back_populates="squad",
        cascade="all, delete-orphan",
    )
    picks = relationship(
        "FantasyMatchdayPick",
        back_populates="squad",
        cascade="all, delete-orphan",
    )
    transfers = relationship(
        "FantasyTransfer",
        back_populates="squad",
        cascade="all, delete-orphan",
    )
    points_history = relationship(
        "FantasyPointsHistory",
        back_populates="squad",
        cascade="all, delete-orphan",
    )
    summaries = relationship(
        "FantasyMatchdaySummary",
        back_populates="squad",
        cascade="all, delete-orphan",
    )


class FantasySquadPlayer(Base):
    __tablename__ = "fantasy_squad_players"

    id = Column(Integer, primary_key=True, index=True)
    squad_id = Column(Integer, ForeignKey("fantasy_player_squads.id"), nullable=False, index=True)
    player_id = Column(Integer, ForeignKey("players.id"), nullable=False, index=True)
    position_key = Column(String(8), nullable=False)
    purchase_price = Column(Numeric(10, 2), nullable=False)
    is_active = Column(Boolean, nullable=False, default=True, index=True)
    acquired_at = Column(DateTime, default=datetime.datetime.utcnow, nullable=False)
    released_at = Column(DateTime, nullable=True)

    squad = relationship("FantasyPlayerSquad", back_populates="players")
    player = relationship("Player")


class FantasyMatchdayPick(Base):
    __tablename__ = "fantasy_matchday_picks"
    __table_args__ = (
        UniqueConstraint("squad_id", "matchday_key", "player_id", name="uq_fantasy_matchday_pick"),
    )

    id = Column(Integer, primary_key=True, index=True)
    squad_id = Column(Integer, ForeignKey("fantasy_player_squads.id"), nullable=False, index=True)
    matchday_key = Column(Date, nullable=False, index=True)
    player_id = Column(Integer, ForeignKey("players.id"), nullable=False, index=True)
    role = Column(String(16), nullable=False, default="starter")
    bench_order = Column(Integer, nullable=True)
    is_captain = Column(Boolean, nullable=False, default=False)
    is_vice_captain = Column(Boolean, nullable=False, default=False)
    created_at = Column(DateTime, default=datetime.datetime.utcnow, nullable=False)
    updated_at = Column(
        DateTime,
        default=datetime.datetime.utcnow,
        onupdate=datetime.datetime.utcnow,
        nullable=False,
    )

    squad = relationship("FantasyPlayerSquad", back_populates="picks")
    player = relationship("Player")


class FantasyTransfer(Base):
    __tablename__ = "fantasy_transfers"

    id = Column(Integer, primary_key=True, index=True)
    squad_id = Column(Integer, ForeignKey("fantasy_player_squads.id"), nullable=False, index=True)
    matchday_key = Column(Date, nullable=False, index=True)
    out_player_id = Column(Integer, ForeignKey("players.id"), nullable=False)
    in_player_id = Column(Integer, ForeignKey("players.id"), nullable=False)
    price_out = Column(Numeric(10, 2), nullable=False)
    price_in = Column(Numeric(10, 2), nullable=False)
    penalty_points = Column(Integer, nullable=False, default=0)
    created_at = Column(DateTime, default=datetime.datetime.utcnow, nullable=False)

    squad = relationship("FantasyPlayerSquad", back_populates="transfers")
    out_player = relationship("Player", foreign_keys=[out_player_id])
    in_player = relationship("Player", foreign_keys=[in_player_id])


class FantasyPointsHistory(Base):
    __tablename__ = "fantasy_points_history"

    id = Column(Integer, primary_key=True, index=True)
    squad_id = Column(Integer, ForeignKey("fantasy_player_squads.id"), nullable=False, index=True)
    user_id = Column(Integer, ForeignKey("users.id"), nullable=False, index=True)
    matchday_key = Column(Date, nullable=False, index=True)
    player_id = Column(Integer, ForeignKey("players.id"), nullable=True)
    match_id = Column(Integer, ForeignKey("matches.id"), nullable=True)
    points = Column(Integer, nullable=False, default=0)
    reason = Column(String(64), nullable=False)
    created_at = Column(DateTime, default=datetime.datetime.utcnow, nullable=False)

    squad = relationship("FantasyPlayerSquad", back_populates="points_history")
    user = relationship("User")
    player = relationship("Player")
    match = relationship("Match")


class FantasyMatchdaySummary(Base):
    __tablename__ = "fantasy_matchday_summaries"
    __table_args__ = (
        UniqueConstraint("squad_id", "matchday_key", name="uq_fantasy_matchday_summary"),
    )

    id = Column(Integer, primary_key=True, index=True)
    squad_id = Column(Integer, ForeignKey("fantasy_player_squads.id"), nullable=False, index=True)
    user_id = Column(Integer, ForeignKey("users.id"), nullable=False, index=True)
    matchday_key = Column(Date, nullable=False, index=True)
    total_points = Column(Integer, nullable=False, default=0)
    captain_player_id = Column(Integer, ForeignKey("players.id"), nullable=True)
    transfers_used = Column(Integer, nullable=False, default=0)
    transfer_penalty = Column(Integer, nullable=False, default=0)
    computed_at = Column(DateTime, default=datetime.datetime.utcnow, nullable=False)

    squad = relationship("FantasyPlayerSquad", back_populates="summaries")
    user = relationship("User")
    captain = relationship("Player")
