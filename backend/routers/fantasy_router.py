from datetime import date, datetime, timezone
from decimal import Decimal
from typing import Any, Dict, List, Optional, Sequence, Set, Tuple

from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import BaseModel
from sqlalchemy import func, or_
from sqlalchemy.orm import Session

try:
    from backend.auth import get_current_user
    from backend.database import get_db
    from backend.models import (
        FantasyMatchdayPick,
        FantasyMatchdaySummary,
        FantasyPlayerSquad,
        FantasyPointsHistory,
        FantasySelection,
        FantasySquadPlayer,
        FantasyTransfer,
        League,
        Match,
        MatchEvent,
        Player,
        Team,
        User,
    )
    from backend.schemas import (
        FantasyLeaderboardResponse,
        FantasyMatchdayPicksRequest,
        FantasyMatchdayPicksResponse,
        FantasyMatchdayPointsResponse,
        FantasyPlayerPoolItem,
        FantasyRulesResponse,
        FantasySquadCreateRequest,
        FantasySquadResponse,
        FantasyTransferRequest,
        FantasyTransferResponse,
    )
    from backend.services.fantasy_rules_engine import (
        CLEAN_SHEET_POINTS_BY_POSITION,
        EXTRA_TRANSFER_PENALTY,
        FANTASY_BUDGET_CAP,
        FANTASY_SQUAD_SIZE,
        FINISHED_MATCH_STATUSES,
        FREE_TRANSFERS_PER_MATCHDAY,
        GOAL_POINTS_BY_POSITION,
        SQUAD_POSITION_LIMITS,
        STARTING_POSITION_LIMITS,
        SUPPORTED_COMPETITION_LEAGUE_IDS,
        SUPPORTED_LEAGUE_NAME_TOKENS,
        FantasyRuleError,
        calculate_player_price,
        compute_matchday_points,
        decimalize,
        is_matchday_locked,
        normalize_position,
        parse_matchday_key,
        transfer_penalty,
        validate_matchday_picks,
        validate_squad,
        validate_transfer_batch,
    )
except ImportError:
    from auth import get_current_user
    from database import get_db
    from models import (
        FantasyMatchdayPick,
        FantasyMatchdaySummary,
        FantasyPlayerSquad,
        FantasyPointsHistory,
        FantasySelection,
        FantasySquadPlayer,
        FantasyTransfer,
        League,
        Match,
        MatchEvent,
        Player,
        Team,
        User,
    )
    from schemas import (
        FantasyLeaderboardResponse,
        FantasyMatchdayPicksRequest,
        FantasyMatchdayPicksResponse,
        FantasyMatchdayPointsResponse,
        FantasyPlayerPoolItem,
        FantasyRulesResponse,
        FantasySquadCreateRequest,
        FantasySquadResponse,
        FantasyTransferRequest,
        FantasyTransferResponse,
    )
    from services.fantasy_rules_engine import (
        CLEAN_SHEET_POINTS_BY_POSITION,
        EXTRA_TRANSFER_PENALTY,
        FANTASY_BUDGET_CAP,
        FANTASY_SQUAD_SIZE,
        FINISHED_MATCH_STATUSES,
        FREE_TRANSFERS_PER_MATCHDAY,
        GOAL_POINTS_BY_POSITION,
        SQUAD_POSITION_LIMITS,
        STARTING_POSITION_LIMITS,
        SUPPORTED_COMPETITION_LEAGUE_IDS,
        SUPPORTED_LEAGUE_NAME_TOKENS,
        FantasyRuleError,
        calculate_player_price,
        compute_matchday_points,
        decimalize,
        is_matchday_locked,
        normalize_position,
        parse_matchday_key,
        transfer_penalty,
        validate_matchday_picks,
        validate_squad,
        validate_transfer_batch,
    )

router = APIRouter(prefix="/api/v1/fantasy", tags=["fantasy"])


# ---------------------------------------------------------------------------
# Legacy team-based fantasy mode (kept for backwards compatibility)
# ---------------------------------------------------------------------------

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
    db: Session = Depends(get_db),
):
    """Get the current user's selected fantasy teams (legacy mode)."""
    selections = (
        db.query(FantasySelection)
        .filter(FantasySelection.user_id == current_user.id)
        .all()
    )

    teams = [db.query(Team).filter(Team.id == sel.team_id).first() for sel in selections]
    return [team for team in teams if team is not None]


@router.post("/select-teams")
def select_teams(
    request: TeamSelectionRequest,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    """Select 5 teams for legacy fantasy mode."""
    if len(request.team_ids) != 5:
        raise HTTPException(status_code=400, detail="You must select exactly 5 teams")

    teams = db.query(Team).filter(Team.id.in_(request.team_ids)).all()
    if len(teams) != 5:
        raise HTTPException(status_code=400, detail="Some teams do not exist")

    (
        db.query(FantasySelection)
        .filter(FantasySelection.user_id == current_user.id)
        .delete(synchronize_session=False)
    )

    for team_id in request.team_ids:
        db.add(FantasySelection(user_id=current_user.id, team_id=team_id))

    db.commit()
    return {"message": "Teams selected successfully"}


@router.get("/my-points")
def get_my_points(
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    """Calculate points for legacy team-based mode."""
    selections = (
        db.query(FantasySelection)
        .filter(FantasySelection.user_id == current_user.id)
        .all()
    )

    if not selections:
        return {"points": 0, "message": "No teams selected yet"}

    team_ids = [selection.team_id for selection in selections]
    total_points = 0

    for team_id in team_ids:
        home_wins = (
            db.query(Match)
            .filter(
                Match.home_team_id == team_id,
                Match.status == "FT",
                Match.home_score > Match.away_score,
            )
            .count()
        )

        away_wins = (
            db.query(Match)
            .filter(
                Match.away_team_id == team_id,
                Match.status == "FT",
                Match.away_score > Match.home_score,
            )
            .count()
        )

        home_draws = (
            db.query(Match)
            .filter(
                Match.home_team_id == team_id,
                Match.status == "FT",
                Match.home_score == Match.away_score,
            )
            .count()
        )

        away_draws = (
            db.query(Match)
            .filter(
                Match.away_team_id == team_id,
                Match.status == "FT",
                Match.away_score == Match.home_score,
            )
            .count()
        )

        total_points += (home_wins + away_wins) * 3 + (home_draws + away_draws)

    return {"points": total_points}


@router.get("/leaderboard", response_model=List[LeaderboardEntry])
def get_leaderboard(db: Session = Depends(get_db)):
    """Get leaderboard for legacy team-based mode."""
    users_with_selections = db.query(User).join(FantasySelection).distinct().all()

    leaderboard: List[Dict[str, Any]] = []

    for user in users_with_selections:
        selections = (
            db.query(FantasySelection)
            .filter(FantasySelection.user_id == user.id)
            .all()
        )

        team_ids = [selection.team_id for selection in selections]

        team_names: List[str] = []
        for team_id in team_ids:
            team = db.query(Team).filter(Team.id == team_id).first()
            if team:
                team_names.append(team.name)

        total_points = 0
        for team_id in team_ids:
            home_wins = (
                db.query(Match)
                .filter(
                    Match.home_team_id == team_id,
                    Match.status == "FT",
                    Match.home_score > Match.away_score,
                )
                .count()
            )

            away_wins = (
                db.query(Match)
                .filter(
                    Match.away_team_id == team_id,
                    Match.status == "FT",
                    Match.away_score > Match.home_score,
                )
                .count()
            )

            home_draws = (
                db.query(Match)
                .filter(
                    Match.home_team_id == team_id,
                    Match.status == "FT",
                    Match.home_score == Match.away_score,
                )
                .count()
            )

            away_draws = (
                db.query(Match)
                .filter(
                    Match.away_team_id == team_id,
                    Match.status == "FT",
                    Match.away_score == Match.home_score,
                )
                .count()
            )

            total_points += (home_wins + away_wins) * 3 + (home_draws + away_draws)

        leaderboard.append(
            {
                "username": user.username,
                "points": total_points,
                "teams": team_names,
            }
        )

    leaderboard.sort(key=lambda entry: entry["points"], reverse=True)
    return leaderboard


# ---------------------------------------------------------------------------
# Player-based fantasy mode
# ---------------------------------------------------------------------------


def _supported_league_clause():
    league_name_filters = [League.name.ilike(f"%{token}%") for token in SUPPORTED_LEAGUE_NAME_TOKENS]
    return or_(League.id.in_(list(SUPPORTED_COMPETITION_LEAGUE_IDS)), *league_name_filters)


def _get_or_create_player_squad(user: User, db: Session) -> FantasyPlayerSquad:
    squad = db.query(FantasyPlayerSquad).filter(FantasyPlayerSquad.user_id == user.id).first()

    if squad:
        return squad

    squad = FantasyPlayerSquad(
        user_id=user.id,
        budget_cap=decimalize(FANTASY_BUDGET_CAP),
        budget_spent=decimalize(Decimal("0.00")),
    )
    db.add(squad)
    db.commit()
    db.refresh(squad)
    return squad


def _active_squad_player_rows(squad_id: int, db: Session):
    return (
        db.query(FantasySquadPlayer, Player, Team)
        .join(Player, FantasySquadPlayer.player_id == Player.id)
        .join(Team, Player.team_id == Team.id)
        .filter(
            FantasySquadPlayer.squad_id == squad_id,
            FantasySquadPlayer.is_active.is_(True),
        )
        .all()
    )


def _serialize_squad(squad: FantasyPlayerSquad, db: Session) -> Dict[str, Any]:
    rows = _active_squad_player_rows(squad.id, db)

    position_order = {"GK": 0, "DEF": 1, "MID": 2, "FWD": 3}

    players_payload = [
        {
            "player_id": player.id,
            "player_name": player.name,
            "position_key": squad_player.position_key,
            "team_id": team.id,
            "team_name": team.name,
            "team_logo": team.logo_url,
            "purchase_price": float(decimalize(squad_player.purchase_price)),
            "is_active": bool(squad_player.is_active),
        }
        for squad_player, player, team in rows
    ]

    players_payload.sort(
        key=lambda entry: (
            position_order.get(entry["position_key"], 99),
            entry["purchase_price"] * -1,
            entry["player_name"],
        )
    )

    budget_cap = decimalize(squad.budget_cap)
    budget_spent = decimalize(squad.budget_spent)

    return {
        "squad_id": squad.id,
        "user_id": squad.user_id,
        "budget_cap": float(budget_cap),
        "budget_spent": float(budget_spent),
        "budget_remaining": float(decimalize(budget_cap - budget_spent)),
        "created_at": squad.created_at,
        "updated_at": squad.updated_at,
        "players": players_payload,
    }


def _parse_matchday_or_today(matchday_key: Optional[str]) -> date:
    if matchday_key:
        try:
            return parse_matchday_key(matchday_key)
        except FantasyRuleError as exc:
            raise HTTPException(status_code=400, detail=str(exc)) from exc

    return datetime.now(timezone.utc).date()


def _fetch_supported_player_rows(player_ids: Sequence[int], db: Session):
    if not player_ids:
        return []

    return (
        db.query(Player, Team, League)
        .join(Team, Player.team_id == Team.id)
        .join(League, Team.league_id == League.id)
        .filter(Player.id.in_(list({int(player_id) for player_id in player_ids})), _supported_league_clause())
        .all()
    )


def _upsert_default_matchday_picks(
    squad: FantasyPlayerSquad,
    matchday_date: date,
    db: Session,
) -> None:
    active_rows = _active_squad_player_rows(squad.id, db)
    if len(active_rows) != FANTASY_SQUAD_SIZE:
        return

    by_position: Dict[str, List[Tuple[FantasySquadPlayer, Player, Team]]] = {
        "GK": [],
        "DEF": [],
        "MID": [],
        "FWD": [],
    }

    for row in active_rows:
        squad_player, player, team = row
        position_key = squad_player.position_key or normalize_position(player.position)
        if position_key not in by_position:
            continue
        by_position[position_key].append(row)

    if any(len(by_position[position_key]) < minimum for position_key, minimum in {
        "GK": 1,
        "DEF": 3,
        "MID": 2,
        "FWD": 1,
    }.items()):
        return

    for position_key in by_position:
        by_position[position_key].sort(
            key=lambda row: (float(decimalize(row[0].purchase_price)) * -1, row[1].name)
        )

    starters: List[Tuple[FantasySquadPlayer, Player, Team]] = []
    starters.extend(by_position["GK"][:1])
    starters.extend(by_position["DEF"][:3])
    starters.extend(by_position["MID"][:4])
    starters.extend(by_position["FWD"][:3])

    starter_ids = {row[1].id for row in starters}
    bench = [row for row in active_rows if row[1].id not in starter_ids]

    if len(starters) != 11 or len(bench) != 4:
        return

    sorted_starters = sorted(
        starters,
        key=lambda row: (float(decimalize(row[0].purchase_price)) * -1, row[1].id),
    )

    captain_id = sorted_starters[0][1].id
    vice_captain_id = sorted_starters[1][1].id if len(sorted_starters) > 1 else None

    for row in starters:
        _, player, _ = row
        db.add(
            FantasyMatchdayPick(
                squad_id=squad.id,
                matchday_key=matchday_date,
                player_id=player.id,
                role="starter",
                bench_order=None,
                is_captain=player.id == captain_id,
                is_vice_captain=player.id == vice_captain_id,
            )
        )

    bench.sort(key=lambda row: (row[0].position_key, row[1].name))
    for bench_index, row in enumerate(bench, start=1):
        _, player, _ = row
        db.add(
            FantasyMatchdayPick(
                squad_id=squad.id,
                matchday_key=matchday_date,
                player_id=player.id,
                role="bench",
                bench_order=bench_index,
                is_captain=False,
                is_vice_captain=False,
            )
        )

    db.commit()


def _matchday_picks_payload(
    squad: FantasyPlayerSquad,
    matchday_date: date,
    db: Session,
) -> List[Dict[str, Any]]:
    rows = (
        db.query(FantasyMatchdayPick, Player)
        .join(Player, FantasyMatchdayPick.player_id == Player.id)
        .filter(
            FantasyMatchdayPick.squad_id == squad.id,
            FantasyMatchdayPick.matchday_key == matchday_date,
        )
        .all()
    )

    if not rows:
        return []

    active_position_map = {
        row[1].id: row[0].position_key
        for row in _active_squad_player_rows(squad.id, db)
    }

    payload = []
    for pick, player in rows:
        payload.append(
            {
                "player_id": player.id,
                "player_name": player.name,
                "position_key": active_position_map.get(player.id, normalize_position(player.position)),
                "role": pick.role,
                "bench_order": pick.bench_order,
                "is_captain": bool(pick.is_captain),
                "is_vice_captain": bool(pick.is_vice_captain),
            }
        )

    role_order = {"starter": 0, "bench": 1}
    payload.sort(
        key=lambda entry: (
            role_order.get(entry["role"], 99),
            entry["bench_order"] if entry["bench_order"] is not None else 0,
            entry["player_name"],
        )
    )

    return payload


def _compute_and_persist_matchday_points(
    squad: FantasyPlayerSquad,
    user_id: int,
    matchday_date: date,
    db: Session,
) -> Dict[str, Any]:
    picks = (
        db.query(FantasyMatchdayPick)
        .filter(
            FantasyMatchdayPick.squad_id == squad.id,
            FantasyMatchdayPick.matchday_key == matchday_date,
        )
        .all()
    )

    if not picks:
        _upsert_default_matchday_picks(squad, matchday_date, db)
        picks = (
            db.query(FantasyMatchdayPick)
            .filter(
                FantasyMatchdayPick.squad_id == squad.id,
                FantasyMatchdayPick.matchday_key == matchday_date,
            )
            .all()
        )

    starters = [pick for pick in picks if pick.role == "starter"]
    captain_pick = next((pick for pick in starters if pick.is_captain), None)

    starter_ids = [pick.player_id for pick in starters]

    starter_rows = []
    if starter_ids:
        starter_rows = (
            db.query(Player, Team)
            .join(Team, Player.team_id == Team.id)
            .filter(Player.id.in_(starter_ids))
            .all()
        )

    player_map = {player.id: (player, team) for player, team in starter_rows}
    starter_payload = []

    for pick in starters:
        mapped = player_map.get(pick.player_id)
        if not mapped:
            continue
        player, team = mapped
        starter_payload.append(
            {
                "player_id": player.id,
                "player_name": player.name,
                "team_id": team.id,
                "position_key": normalize_position(player.position),
            }
        )

    match_rows = (
        db.query(Match)
        .join(Team, Match.home_team_id == Team.id)
        .join(League, Team.league_id == League.id)
        .filter(
            func.date(Match.start_time) == matchday_date,
            Match.status.in_(list(FINISHED_MATCH_STATUSES)),
            _supported_league_clause(),
        )
        .all()
    )

    match_ids = [match.id for match in match_rows]
    events_by_match: Dict[int, List[MatchEvent]] = {match_id: [] for match_id in match_ids}

    if match_ids:
        event_rows = (
            db.query(MatchEvent)
            .filter(MatchEvent.match_id.in_(match_ids))
            .order_by(MatchEvent.minute.asc(), MatchEvent.id.asc())
            .all()
        )
        for event in event_rows:
            events_by_match.setdefault(event.match_id, []).append(event)

    raw_points, entries = compute_matchday_points(
        starters=starter_payload,
        captain_player_id=captain_pick.player_id if captain_pick else None,
        finished_matches=match_rows,
        events_by_match=events_by_match,
    )

    transfer_count = (
        db.query(FantasyTransfer)
        .filter(
            FantasyTransfer.squad_id == squad.id,
            FantasyTransfer.matchday_key == matchday_date,
        )
        .count()
    )
    transfer_penalty_points = transfer_penalty(transfer_count)

    total_points = raw_points - transfer_penalty_points

    (
        db.query(FantasyPointsHistory)
        .filter(
            FantasyPointsHistory.squad_id == squad.id,
            FantasyPointsHistory.user_id == user_id,
            FantasyPointsHistory.matchday_key == matchday_date,
        )
        .delete(synchronize_session=False)
    )

    for entry in entries:
        db.add(
            FantasyPointsHistory(
                squad_id=squad.id,
                user_id=user_id,
                matchday_key=matchday_date,
                player_id=entry.get("player_id"),
                match_id=entry.get("match_id"),
                points=int(entry.get("points", 0)),
                reason=str(entry.get("reason", "score")),
            )
        )

    if transfer_penalty_points > 0:
        db.add(
            FantasyPointsHistory(
                squad_id=squad.id,
                user_id=user_id,
                matchday_key=matchday_date,
                player_id=None,
                match_id=None,
                points=-int(transfer_penalty_points),
                reason="transfer_penalty",
            )
        )

    summary = (
        db.query(FantasyMatchdaySummary)
        .filter(
            FantasyMatchdaySummary.squad_id == squad.id,
            FantasyMatchdaySummary.matchday_key == matchday_date,
        )
        .first()
    )

    if summary is None:
        summary = FantasyMatchdaySummary(
            squad_id=squad.id,
            user_id=user_id,
            matchday_key=matchday_date,
            total_points=total_points,
            captain_player_id=captain_pick.player_id if captain_pick else None,
            transfers_used=transfer_count,
            transfer_penalty=transfer_penalty_points,
        )
        db.add(summary)
    else:
        summary.total_points = total_points
        summary.captain_player_id = captain_pick.player_id if captain_pick else None
        summary.transfers_used = transfer_count
        summary.transfer_penalty = transfer_penalty_points
        summary.computed_at = datetime.utcnow()

    db.commit()

    history_rows = (
        db.query(FantasyPointsHistory, Player)
        .outerjoin(Player, FantasyPointsHistory.player_id == Player.id)
        .filter(
            FantasyPointsHistory.squad_id == squad.id,
            FantasyPointsHistory.user_id == user_id,
            FantasyPointsHistory.matchday_key == matchday_date,
        )
        .order_by(FantasyPointsHistory.id.asc())
        .all()
    )

    history_payload = []
    for history_row, player in history_rows:
        history_payload.append(
            {
                "player_id": history_row.player_id,
                "player_name": player.name if player else None,
                "match_id": history_row.match_id,
                "points": int(history_row.points),
                "reason": history_row.reason,
            }
        )

    return {
        "matchday_key": matchday_date,
        "total_points": int(total_points),
        "transfer_penalty": int(transfer_penalty_points),
        "captain_player_id": captain_pick.player_id if captain_pick else None,
        "entries": history_payload,
    }


@router.get("/player-mode/rules", response_model=FantasyRulesResponse)
def get_player_mode_rules():
    return {
        "squad_size": FANTASY_SQUAD_SIZE,
        "budget_cap": float(decimalize(FANTASY_BUDGET_CAP)),
        "position_limits": dict(SQUAD_POSITION_LIMITS),
        "starting_limits": {
            position: {"min": min_max[0], "max": min_max[1]}
            for position, min_max in STARTING_POSITION_LIMITS.items()
        },
        "free_transfers_per_matchday": FREE_TRANSFERS_PER_MATCHDAY,
        "extra_transfer_penalty": EXTRA_TRANSFER_PENALTY,
        "scoring_rules": {
            "appearance": 2,
            "assist": 3,
            "yellow_card": -1,
            "red_card": -3,
            "own_goal_penalty": -2,
            "captain_multiplier": 2,
            "goal_gk": GOAL_POINTS_BY_POSITION["GK"],
            "goal_def": GOAL_POINTS_BY_POSITION["DEF"],
            "goal_mid": GOAL_POINTS_BY_POSITION["MID"],
            "goal_fwd": GOAL_POINTS_BY_POSITION["FWD"],
            "clean_sheet_gk": CLEAN_SHEET_POINTS_BY_POSITION["GK"],
            "clean_sheet_def": CLEAN_SHEET_POINTS_BY_POSITION["DEF"],
            "clean_sheet_mid": CLEAN_SHEET_POINTS_BY_POSITION["MID"],
        },
    }


@router.get("/player-mode/players", response_model=List[FantasyPlayerPoolItem])
def list_player_mode_pool(
    search: Optional[str] = Query(None),
    position: Optional[str] = Query(None),
    skip: int = Query(0, ge=0),
    limit: int = Query(150, ge=1, le=500),
    db: Session = Depends(get_db),
):
    query = (
        db.query(Player, Team, League)
        .join(Team, Player.team_id == Team.id)
        .join(League, Team.league_id == League.id)
        .filter(_supported_league_clause())
    )

    if search:
        query = query.filter(Player.name.ilike(f"%{search}%"))

    if position:
        query = query.filter(Player.position.ilike(f"%{position}%"))

    rows = query.offset(skip).limit(limit).all()

    result = []
    for player, team, league in rows:
        result.append(
            {
                "player_id": player.id,
                "player_name": player.name,
                "position_key": normalize_position(player.position),
                "team_id": team.id,
                "team_name": team.name,
                "team_logo": team.logo_url,
                "league_id": league.id,
                "league_name": league.name,
                "price": float(calculate_player_price(player)),
                "goals_season": int(player.goals_season or 0),
                "assists_season": int(player.assists_season or 0),
                "rating_season": float(player.rating_season) if player.rating_season is not None else None,
                "minutes_played": int(player.minutes_played or 0),
            }
        )

    return result


@router.get("/player-mode/squad", response_model=FantasySquadResponse)
def get_player_mode_squad(
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    squad = _get_or_create_player_squad(current_user, db)
    return _serialize_squad(squad, db)


@router.post("/player-mode/squad", response_model=FantasySquadResponse)
def save_player_mode_squad(
    request: FantasySquadCreateRequest,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    if not request.player_ids:
        raise HTTPException(status_code=400, detail="player_ids cannot be empty")

    supported_rows = _fetch_supported_player_rows(request.player_ids, db)
    row_by_player_id = {player.id: (player, team, league) for player, team, league in supported_rows}

    selected_players: List[Player] = []
    position_map: Dict[int, str] = {}
    team_map: Dict[int, int] = {}
    price_map: Dict[int, Decimal] = {}

    for player_id in request.player_ids:
        row = row_by_player_id.get(player_id)
        if row is None:
            raise HTTPException(
                status_code=400,
                detail=f"Player {player_id} is missing or outside Top 5 + UCL scope",
            )

        player, team, _ = row
        selected_players.append(player)

        if player.id not in position_map:
            position_map[player.id] = normalize_position(player.position)
            team_map[player.id] = team.id
            price_map[player.id] = calculate_player_price(player)

    try:
        summary = validate_squad(
            players=selected_players,
            position_map=position_map,
            team_map=team_map,
            price_map=price_map,
            budget_cap=FANTASY_BUDGET_CAP,
        )
    except FantasyRuleError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc

    squad = _get_or_create_player_squad(current_user, db)

    now = datetime.utcnow()

    active_rows = (
        db.query(FantasySquadPlayer)
        .filter(
            FantasySquadPlayer.squad_id == squad.id,
            FantasySquadPlayer.is_active.is_(True),
        )
        .all()
    )
    for row in active_rows:
        row.is_active = False
        row.released_at = now

    future_date = datetime.now(timezone.utc).date()
    (
        db.query(FantasyMatchdayPick)
        .filter(
            FantasyMatchdayPick.squad_id == squad.id,
            FantasyMatchdayPick.matchday_key >= future_date,
        )
        .delete(synchronize_session=False)
    )

    for player_id in request.player_ids:
        player = row_by_player_id[player_id][0]
        db.add(
            FantasySquadPlayer(
                squad_id=squad.id,
                player_id=player.id,
                position_key=normalize_position(player.position),
                purchase_price=price_map[player.id],
                is_active=True,
                acquired_at=now,
            )
        )

    squad.budget_cap = decimalize(FANTASY_BUDGET_CAP)
    squad.budget_spent = summary.spent

    db.commit()
    db.refresh(squad)

    return _serialize_squad(squad, db)


@router.get("/player-mode/matchday/{matchday_key}/picks", response_model=FantasyMatchdayPicksResponse)
def get_matchday_picks(
    matchday_key: str,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    matchday_date = _parse_matchday_or_today(matchday_key)
    squad = _get_or_create_player_squad(current_user, db)

    if not _active_squad_player_rows(squad.id, db):
        raise HTTPException(status_code=400, detail="Create your 15-player squad before setting matchday picks")

    picks_payload = _matchday_picks_payload(squad, matchday_date, db)
    if not picks_payload:
        _upsert_default_matchday_picks(squad, matchday_date, db)
        picks_payload = _matchday_picks_payload(squad, matchday_date, db)

    return {
        "matchday_key": matchday_date,
        "is_locked": is_matchday_locked(matchday_date, db),
        "picks": picks_payload,
    }


@router.put("/player-mode/matchday/{matchday_key}/picks", response_model=FantasyMatchdayPicksResponse)
def save_matchday_picks(
    matchday_key: str,
    request: FantasyMatchdayPicksRequest,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    matchday_date = _parse_matchday_or_today(matchday_key)

    if is_matchday_locked(matchday_date, db):
        raise HTTPException(status_code=423, detail="Matchday is locked. Picks cannot be updated after deadline")

    squad = _get_or_create_player_squad(current_user, db)
    active_rows = _active_squad_player_rows(squad.id, db)

    if len(active_rows) != FANTASY_SQUAD_SIZE:
        raise HTTPException(status_code=400, detail="You must have a valid 15-player squad before setting picks")

    active_player_ids: Set[int] = {player.id for _, player, _ in active_rows}
    active_position_map = {player.id: squad_player.position_key for squad_player, player, _ in active_rows}

    picks_payload = [
        {
            "player_id": pick.player_id,
            "role": pick.role,
            "bench_order": pick.bench_order,
            "is_captain": pick.is_captain,
            "is_vice_captain": pick.is_vice_captain,
        }
        for pick in request.picks
    ]

    try:
        validate_matchday_picks(
            squad_player_ids=active_player_ids,
            player_positions=active_position_map,
            picks=picks_payload,
        )
    except FantasyRuleError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc

    (
        db.query(FantasyMatchdayPick)
        .filter(
            FantasyMatchdayPick.squad_id == squad.id,
            FantasyMatchdayPick.matchday_key == matchday_date,
        )
        .delete(synchronize_session=False)
    )

    for pick in request.picks:
        db.add(
            FantasyMatchdayPick(
                squad_id=squad.id,
                matchday_key=matchday_date,
                player_id=pick.player_id,
                role=pick.role,
                bench_order=pick.bench_order,
                is_captain=pick.is_captain,
                is_vice_captain=pick.is_vice_captain,
            )
        )

    db.commit()

    return {
        "matchday_key": matchday_date,
        "is_locked": is_matchday_locked(matchday_date, db),
        "picks": _matchday_picks_payload(squad, matchday_date, db),
    }


@router.post("/player-mode/matchday/{matchday_key}/transfers", response_model=FantasyTransferResponse)
def apply_matchday_transfers(
    matchday_key: str,
    request: FantasyTransferRequest,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    if not request.transfers:
        raise HTTPException(status_code=400, detail="At least one transfer is required")

    matchday_date = _parse_matchday_or_today(matchday_key)

    if is_matchday_locked(matchday_date, db):
        raise HTTPException(status_code=423, detail="Matchday is locked. Transfers are not allowed after deadline")

    squad = _get_or_create_player_squad(current_user, db)
    active_rows = _active_squad_player_rows(squad.id, db)

    if len(active_rows) != FANTASY_SQUAD_SIZE:
        raise HTTPException(status_code=400, detail="You must have a valid 15-player squad before making transfers")

    active_by_player_id = {player.id: (squad_player, player, team) for squad_player, player, team in active_rows}

    outgoing_ids = [item.out_player_id for item in request.transfers]
    incoming_ids = [item.in_player_id for item in request.transfers]

    incoming_rows = _fetch_supported_player_rows(incoming_ids, db)
    incoming_by_player_id = {player.id: (player, team, league) for player, team, league in incoming_rows}

    for incoming_id in incoming_ids:
        if incoming_id not in incoming_by_player_id:
            raise HTTPException(
                status_code=400,
                detail=f"Incoming player {incoming_id} is missing or outside Top 5 + UCL scope",
            )

    transfer_pairs = [(item.out_player_id, item.in_player_id) for item in request.transfers]

    active_player_ids = set(active_by_player_id.keys())
    active_position_map = {player_id: row[0].position_key for player_id, row in active_by_player_id.items()}
    active_team_map = {player_id: row[2].id for player_id, row in active_by_player_id.items()}

    incoming_position_map = {
        player_id: normalize_position(row[0].position)
        for player_id, row in incoming_by_player_id.items()
    }
    incoming_team_map = {
        player_id: row[1].id
        for player_id, row in incoming_by_player_id.items()
    }

    try:
        validate_transfer_batch(
            active_player_ids=active_player_ids,
            active_position_map=active_position_map,
            active_team_map=active_team_map,
            incoming_position_map=incoming_position_map,
            incoming_team_map=incoming_team_map,
            transfer_pairs=transfer_pairs,
        )
    except FantasyRuleError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc

    current_spent = decimalize(squad.budget_spent)
    total_out = Decimal("0.00")
    total_in = Decimal("0.00")

    for out_player_id, in_player_id in transfer_pairs:
        outgoing_row = active_by_player_id[out_player_id]
        incoming_player = incoming_by_player_id[in_player_id][0]

        total_out += decimalize(outgoing_row[0].purchase_price)
        total_in += calculate_player_price(incoming_player)

    projected_spent = decimalize(current_spent - total_out + total_in)
    if projected_spent > decimalize(squad.budget_cap):
        raise HTTPException(
            status_code=400,
            detail=(
                f"Transfer exceeds budget cap. New spent would be {projected_spent}, "
                f"cap is {decimalize(squad.budget_cap)}"
            ),
        )

    existing_transfer_count = (
        db.query(FantasyTransfer)
        .filter(
            FantasyTransfer.squad_id == squad.id,
            FantasyTransfer.matchday_key == matchday_date,
        )
        .count()
    )

    now = datetime.utcnow()

    for index, (out_player_id, in_player_id) in enumerate(transfer_pairs, start=1):
        outgoing_squad_player, _, _ = active_by_player_id[out_player_id]
        incoming_player, _, _ = incoming_by_player_id[in_player_id]

        outgoing_squad_player.is_active = False
        outgoing_squad_player.released_at = now

        incoming_price = calculate_player_price(incoming_player)
        incoming_position = normalize_position(incoming_player.position)

        db.add(
            FantasySquadPlayer(
                squad_id=squad.id,
                player_id=incoming_player.id,
                position_key=incoming_position,
                purchase_price=incoming_price,
                is_active=True,
                acquired_at=now,
            )
        )

        current_transfer_number = existing_transfer_count + index
        previous_transfer_number = current_transfer_number - 1
        transfer_penalty_points = transfer_penalty(current_transfer_number) - transfer_penalty(previous_transfer_number)

        db.add(
            FantasyTransfer(
                squad_id=squad.id,
                matchday_key=matchday_date,
                out_player_id=out_player_id,
                in_player_id=in_player_id,
                price_out=decimalize(outgoing_squad_player.purchase_price),
                price_in=incoming_price,
                penalty_points=transfer_penalty_points,
                created_at=now,
            )
        )

    (
        db.query(FantasyMatchdayPick)
        .filter(
            FantasyMatchdayPick.squad_id == squad.id,
            FantasyMatchdayPick.matchday_key == matchday_date,
        )
        .delete(synchronize_session=False)
    )

    squad.budget_spent = projected_spent

    db.commit()
    db.refresh(squad)

    transfers_used = existing_transfer_count + len(transfer_pairs)

    return {
        "matchday_key": matchday_date,
        "transfers_used": transfers_used,
        "penalty_points": transfer_penalty(transfers_used),
        "budget_spent": float(decimalize(squad.budget_spent)),
        "budget_remaining": float(decimalize(decimalize(squad.budget_cap) - decimalize(squad.budget_spent))),
    }


@router.get("/player-mode/matchday/{matchday_key}/points", response_model=FantasyMatchdayPointsResponse)
def get_matchday_points(
    matchday_key: str,
    recompute: bool = Query(True, description="Recompute matchday points before returning payload"),
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    matchday_date = _parse_matchday_or_today(matchday_key)
    squad = _get_or_create_player_squad(current_user, db)

    if len(_active_squad_player_rows(squad.id, db)) != FANTASY_SQUAD_SIZE:
        raise HTTPException(status_code=400, detail="You must create a 15-player squad first")

    if recompute:
        return _compute_and_persist_matchday_points(squad, current_user.id, matchday_date, db)

    summary = (
        db.query(FantasyMatchdaySummary)
        .filter(
            FantasyMatchdaySummary.squad_id == squad.id,
            FantasyMatchdaySummary.matchday_key == matchday_date,
        )
        .first()
    )

    if summary is None:
        return _compute_and_persist_matchday_points(squad, current_user.id, matchday_date, db)

    history_rows = (
        db.query(FantasyPointsHistory, Player)
        .outerjoin(Player, FantasyPointsHistory.player_id == Player.id)
        .filter(
            FantasyPointsHistory.squad_id == squad.id,
            FantasyPointsHistory.user_id == current_user.id,
            FantasyPointsHistory.matchday_key == matchday_date,
        )
        .order_by(FantasyPointsHistory.id.asc())
        .all()
    )

    entries = []
    for history_row, player in history_rows:
        entries.append(
            {
                "player_id": history_row.player_id,
                "player_name": player.name if player else None,
                "match_id": history_row.match_id,
                "points": int(history_row.points),
                "reason": history_row.reason,
            }
        )

    return {
        "matchday_key": matchday_date,
        "total_points": int(summary.total_points),
        "transfer_penalty": int(summary.transfer_penalty),
        "captain_player_id": summary.captain_player_id,
        "entries": entries,
    }


@router.get("/player-mode/leaderboard", response_model=FantasyLeaderboardResponse)
def get_player_mode_leaderboard(
    matchday_key: Optional[str] = Query(None, description="YYYY-MM-DD, defaults to current UTC date"),
    refresh_matchday: bool = Query(True, description="Recompute matchday points for all squads before ranking"),
    db: Session = Depends(get_db),
):
    matchday_date = _parse_matchday_or_today(matchday_key)

    squads = db.query(FantasyPlayerSquad).all()

    if refresh_matchday:
        for squad in squads:
            try:
                if len(_active_squad_player_rows(squad.id, db)) == FANTASY_SQUAD_SIZE:
                    _compute_and_persist_matchday_points(squad, squad.user_id, matchday_date, db)
            except Exception:
                # Keep leaderboard resilient even if one squad has inconsistent data.
                db.rollback()

    total_points_rows = (
        db.query(
            FantasyMatchdaySummary.user_id,
            func.coalesce(func.sum(FantasyMatchdaySummary.total_points), 0).label("total_points"),
        )
        .filter(FantasyMatchdaySummary.matchday_key <= matchday_date)
        .group_by(FantasyMatchdaySummary.user_id)
        .all()
    )
    total_points_map = {row.user_id: int(row.total_points or 0) for row in total_points_rows}

    matchday_points_rows = (
        db.query(FantasyMatchdaySummary.user_id, FantasyMatchdaySummary.total_points)
        .filter(FantasyMatchdaySummary.matchday_key == matchday_date)
        .all()
    )
    matchday_points_map = {row.user_id: int(row.total_points or 0) for row in matchday_points_rows}

    squad_size_rows = (
        db.query(FantasyPlayerSquad.user_id, func.count(FantasySquadPlayer.id).label("squad_size"))
        .join(FantasySquadPlayer, FantasyPlayerSquad.id == FantasySquadPlayer.squad_id)
        .filter(FantasySquadPlayer.is_active.is_(True))
        .group_by(FantasyPlayerSquad.user_id)
        .all()
    )
    squad_size_map = {row.user_id: int(row.squad_size or 0) for row in squad_size_rows}

    user_rows = db.query(User).join(FantasyPlayerSquad, User.id == FantasyPlayerSquad.user_id).all()

    entries = []
    for user in user_rows:
        entries.append(
            {
                "username": user.username,
                "total_points": total_points_map.get(user.id, 0),
                "matchday_points": matchday_points_map.get(user.id, 0),
                "squad_size": squad_size_map.get(user.id, 0),
            }
        )

    entries.sort(key=lambda row: (-row["total_points"], -row["matchday_points"], row["username"]))

    ranked_entries = []
    for index, entry in enumerate(entries, start=1):
        ranked_entries.append(
            {
                "rank": index,
                "username": entry["username"],
                "total_points": entry["total_points"],
                "matchday_points": entry["matchday_points"],
                "squad_size": entry["squad_size"],
            }
        )

    return {
        "matchday_key": matchday_date,
        "entries": ranked_entries,
    }
