from pydantic import BaseModel
from typing import List, Optional, Literal, Dict
from datetime import datetime, date

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


class MatchExperienceCompetition(BaseModel):
    id: int
    name: str
    country: Optional[str] = None
    logo_url: Optional[str] = None


class MatchExperienceScore(BaseModel):
    home: Optional[int] = None
    away: Optional[int] = None


class MatchExperienceHeader(BaseModel):
    match_id: int
    start_time: datetime
    status: str
    score: MatchExperienceScore
    competition: Optional[MatchExperienceCompetition] = None


class MatchExperienceTeam(BaseModel):
    id: int
    name: str
    logo_url: Optional[str] = None
    stadium: Optional[str] = None


class MatchExperiencePlayer(BaseModel):
    id: int
    name: str
    position: Optional[str] = None
    photo_url: Optional[str] = None


class MatchExperienceEvent(BaseModel):
    id: int
    minute: int
    event_type: str
    team_id: Optional[int] = None
    player_name: Optional[str] = None
    assist_player: Optional[str] = None
    card_type: Optional[str] = None
    detail: Optional[str] = None


class MatchExperienceSubstitution(BaseModel):
    id: int
    minute: int
    team_id: Optional[int] = None
    player_name: Optional[str] = None
    detail: Optional[str] = None


class MatchExperienceRecentMatch(BaseModel):
    match_id: int
    start_time: datetime
    status: str
    opponent_name: str
    opponent_logo: Optional[str] = None
    is_home: bool
    team_score: Optional[int] = None
    opponent_score: Optional[int] = None
    result: Optional[str] = None
    competition_name: Optional[str] = None


class MatchExperienceLineups(BaseModel):
    home_starting_xi: List[MatchExperiencePlayer]
    away_starting_xi: List[MatchExperiencePlayer]
    substitutions: List[MatchExperienceSubstitution]
    source: str


class MatchExperienceForm(BaseModel):
    home_last_five: List[MatchExperienceRecentMatch]
    away_last_five: List[MatchExperienceRecentMatch]


class MatchExperienceTeams(BaseModel):
    home: MatchExperienceTeam
    away: MatchExperienceTeam


class MatchExperienceSquads(BaseModel):
    home: List[MatchExperiencePlayer]
    away: List[MatchExperiencePlayer]


class MatchExperiencePartialFailure(BaseModel):
    section: str
    message: str


class MatchExperience(BaseModel):
    header: MatchExperienceHeader
    teams: MatchExperienceTeams
    prediction: Optional[Prediction] = None
    events: List[MatchExperienceEvent]
    lineups: MatchExperienceLineups
    form: MatchExperienceForm
    squads: MatchExperienceSquads
    partial_failures: List[MatchExperiencePartialFailure] = []


class NextEventCandidate(BaseModel):
    rank: int
    player_id: int
    player_name: str
    team_id: int
    team_name: str
    probability: float
    full_distribution_probability: float


class NextEventTaskPrediction(BaseModel):
    task: str
    minute_context: int
    source: str
    candidate_count: int
    top_candidates: List[NextEventCandidate]
    top3_probability_mass_from_full_distribution: float
    confidence_score: float
    confidence_label: str
    data_limitations: List[str] = []


class NextEventPredictionResponse(BaseModel):
    match_id: int
    scope: str
    model_version: str
    generated_at_utc: str
    global_limitations: List[str] = []
    next_goal: NextEventTaskPrediction
    next_assist: NextEventTaskPrediction

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


class FantasyPlayerPoolItem(BaseModel):
    player_id: int
    player_name: str
    position_key: str
    team_id: int
    team_name: str
    team_logo: Optional[str] = None
    league_id: Optional[int] = None
    league_name: Optional[str] = None
    price: float
    goals_season: int = 0
    assists_season: int = 0
    rating_season: Optional[float] = None
    minutes_played: int = 0


class FantasyRulesResponse(BaseModel):
    squad_size: int
    budget_cap: float
    position_limits: Dict[str, int]
    starting_limits: Dict[str, Dict[str, int]]
    free_transfers_per_matchday: int
    extra_transfer_penalty: int
    scoring_rules: Dict[str, int]


class FantasySquadCreateRequest(BaseModel):
    player_ids: List[int]


class FantasySquadPlayerResponse(BaseModel):
    player_id: int
    player_name: str
    position_key: str
    team_id: int
    team_name: str
    team_logo: Optional[str] = None
    purchase_price: float
    is_active: bool


class FantasySquadResponse(BaseModel):
    squad_id: int
    user_id: int
    budget_cap: float
    budget_spent: float
    budget_remaining: float
    created_at: datetime
    updated_at: datetime
    players: List[FantasySquadPlayerResponse]


class FantasyMatchdayPickInput(BaseModel):
    player_id: int
    role: Literal["starter", "bench"]
    bench_order: Optional[int] = None
    is_captain: bool = False
    is_vice_captain: bool = False


class FantasyMatchdayPicksRequest(BaseModel):
    picks: List[FantasyMatchdayPickInput]


class FantasyMatchdayPickResponse(BaseModel):
    player_id: int
    player_name: str
    position_key: str
    role: str
    bench_order: Optional[int] = None
    is_captain: bool
    is_vice_captain: bool


class FantasyMatchdayPicksResponse(BaseModel):
    matchday_key: date
    is_locked: bool
    picks: List[FantasyMatchdayPickResponse]


class FantasyTransferItemRequest(BaseModel):
    out_player_id: int
    in_player_id: int


class FantasyTransferRequest(BaseModel):
    transfers: List[FantasyTransferItemRequest]


class FantasyTransferResponse(BaseModel):
    matchday_key: date
    transfers_used: int
    penalty_points: int
    budget_spent: float
    budget_remaining: float


class FantasyPointsHistoryEntryResponse(BaseModel):
    player_id: Optional[int] = None
    player_name: Optional[str] = None
    match_id: Optional[int] = None
    points: int
    reason: str


class FantasyMatchdayPointsResponse(BaseModel):
    matchday_key: date
    total_points: int
    transfer_penalty: int
    captain_player_id: Optional[int] = None
    entries: List[FantasyPointsHistoryEntryResponse]


class FantasyLeaderboardEntry(BaseModel):
    rank: int
    username: str
    total_points: int
    matchday_points: int
    squad_size: int


class FantasyLeaderboardResponse(BaseModel):
    matchday_key: date
    entries: List[FantasyLeaderboardEntry]
