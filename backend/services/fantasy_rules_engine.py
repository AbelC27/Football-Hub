from __future__ import annotations

from collections import Counter, defaultdict
from dataclasses import dataclass
from datetime import date, datetime, time, timezone
from decimal import Decimal, ROUND_HALF_UP
from typing import Any, Dict, Iterable, List, Mapping, Optional, Sequence, Set, Tuple

from sqlalchemy import func
from sqlalchemy.orm import Session

try:
    from backend.models import League, Match, MatchEvent, Player, Team
except ImportError:
    from models import League, Match, MatchEvent, Player, Team


SUPPORTED_COMPETITION_LEAGUE_IDS = {
    39,   # Premier League (API-Football)
    140,  # La Liga (API-Football)
    78,   # Bundesliga (API-Football)
    135,  # Serie A (API-Football)
    61,   # Ligue 1 (API-Football)
    4480, # Champions League (TheSportsDB)
    2021, # Premier League (football-data.org)
    2014, # La Liga (football-data.org)
    2002, # Bundesliga (football-data.org)
    2019, # Serie A (football-data.org)
    2015, # Ligue 1 (football-data.org)
    2001, # Champions League (football-data.org)
}

SUPPORTED_LEAGUE_NAME_TOKENS = (
    "premier league",
    "la liga",
    "bundesliga",
    "serie a",
    "ligue 1",
    "champions league",
)

FANTASY_SQUAD_SIZE = 15
FANTASY_BUDGET_CAP = Decimal("100.00")
FREE_TRANSFERS_PER_MATCHDAY = 1
EXTRA_TRANSFER_PENALTY = 4

SQUAD_POSITION_LIMITS = {
    "GK": 2,
    "DEF": 5,
    "MID": 5,
    "FWD": 3,
}

STARTING_POSITION_LIMITS = {
    "GK": (1, 1),
    "DEF": (3, 5),
    "MID": (2, 5),
    "FWD": (1, 3),
}

GOAL_POINTS_BY_POSITION = {
    "GK": 6,
    "DEF": 6,
    "MID": 5,
    "FWD": 4,
}

CLEAN_SHEET_POINTS_BY_POSITION = {
    "GK": 4,
    "DEF": 4,
    "MID": 1,
    "FWD": 0,
}

FINISHED_MATCH_STATUSES = {"FT", "AET", "PEN"}


class FantasyRuleError(ValueError):
    pass


@dataclass
class SquadValidationSummary:
    spent: Decimal
    remaining: Decimal
    position_counts: Dict[str, int]


def _normalize_text(value: Optional[str]) -> str:
    if not isinstance(value, str):
        return ""
    return value.strip().lower()


def to_utc(dt: datetime) -> datetime:
    if dt.tzinfo is None:
        return dt.replace(tzinfo=timezone.utc)
    return dt.astimezone(timezone.utc)


def parse_matchday_key(matchday_key: str) -> date:
    try:
        return datetime.strptime(matchday_key, "%Y-%m-%d").date()
    except ValueError as exc:
        raise FantasyRuleError("matchday_key must use YYYY-MM-DD format") from exc


def decimalize(value: Any) -> Decimal:
    if isinstance(value, Decimal):
        return value.quantize(Decimal("0.01"), rounding=ROUND_HALF_UP)

    if value is None:
        return Decimal("0.00")

    return Decimal(str(value)).quantize(Decimal("0.01"), rounding=ROUND_HALF_UP)


def normalize_position(position: Optional[str]) -> str:
    pos = _normalize_text(position)

    if not pos:
        return "MID"

    if "goal" in pos or "gk" in pos:
        return "GK"

    if any(token in pos for token in ("def", "back", "centre-back", "full-back", "wing-back", "cb", "rb", "lb")):
        return "DEF"

    if any(token in pos for token in ("mid", "winger", "dm", "cm", "am", "mf")):
        return "MID"

    if any(token in pos for token in ("forward", "striker", "attacker", "fw", "cf")):
        return "FWD"

    return "MID"


def is_supported_league(league: Optional[League]) -> bool:
    if not league:
        return False

    if league.id in SUPPORTED_COMPETITION_LEAGUE_IDS:
        return True

    league_name = _normalize_text(league.name)
    return any(token in league_name for token in SUPPORTED_LEAGUE_NAME_TOKENS)


def is_player_supported_scope(player: Optional[Player], team: Optional[Team], league: Optional[League]) -> bool:
    if not player or not team:
        return False

    return is_supported_league(league)


def resolve_matchday_deadline(matchday_date: date, db: Session) -> datetime:
    rows = (
        db.query(Match.start_time, League.id, League.name)
        .join(Team, Match.home_team_id == Team.id)
        .join(League, Team.league_id == League.id)
        .filter(func.date(Match.start_time) == matchday_date)
        .order_by(Match.start_time.asc())
        .all()
    )

    for start_time, league_id, league_name in rows:
        league_like = type("LeagueLike", (), {"id": league_id, "name": league_name})
        if not is_supported_league(league_like):
            continue
        return to_utc(start_time)

    return datetime.combine(matchday_date, time(hour=12, minute=0, second=0, tzinfo=timezone.utc))


def is_matchday_locked(matchday_date: date, db: Session, now_utc: Optional[datetime] = None) -> bool:
    now = now_utc or datetime.now(timezone.utc)
    deadline = resolve_matchday_deadline(matchday_date, db)
    return now >= deadline


def calculate_player_price(player: Player) -> Decimal:
    position_key = normalize_position(player.position)
    base_price = {
        "GK": Decimal("4.50"),
        "DEF": Decimal("5.00"),
        "MID": Decimal("7.00"),
        "FWD": Decimal("7.50"),
    }[position_key]

    goals = Decimal(str(player.goals_season or 0))
    assists = Decimal(str(player.assists_season or 0))
    rating = Decimal(str(player.rating_season if player.rating_season is not None else 6.0))
    minutes = Decimal(str(player.minutes_played or 0))

    rating_boost = max(Decimal("0.00"), rating - Decimal("6.00")) * Decimal("0.70")
    minutes_ratio = min(minutes, Decimal("3500")) / Decimal("3500")
    minutes_boost = minutes_ratio * Decimal("0.80")

    price = (
        base_price
        + goals * Decimal("0.18")
        + assists * Decimal("0.15")
        + rating_boost
        + minutes_boost
    )

    if minutes < Decimal("180") and goals == 0 and assists == 0:
        price -= Decimal("0.30")

    if price < Decimal("4.00"):
        price = Decimal("4.00")
    if price > Decimal("14.50"):
        price = Decimal("14.50")

    return decimalize(price)


def validate_squad(
    players: Sequence[Player],
    position_map: Mapping[int, str],
    team_map: Mapping[int, int],
    price_map: Mapping[int, Decimal],
    budget_cap: Decimal = FANTASY_BUDGET_CAP,
) -> SquadValidationSummary:
    player_ids = [player.id for player in players]

    if len(player_ids) != FANTASY_SQUAD_SIZE:
        raise FantasyRuleError(f"You must select exactly {FANTASY_SQUAD_SIZE} players")

    if len(set(player_ids)) != len(player_ids):
        raise FantasyRuleError("Duplicate players are not allowed")

    position_counts = Counter(position_map[player.id] for player in players)
    for position_key, required_count in SQUAD_POSITION_LIMITS.items():
        if position_counts.get(position_key, 0) != required_count:
            raise FantasyRuleError(
                f"Squad must include {required_count} {position_key} players"
            )

    team_counts = Counter(team_map[player.id] for player in players)
    if any(count > 3 for count in team_counts.values()):
        raise FantasyRuleError("Maximum 3 players from the same real-world team")

    spent = sum((price_map[player.id] for player in players), Decimal("0.00"))
    spent = decimalize(spent)

    if spent > budget_cap:
        raise FantasyRuleError(
            f"Budget exceeded: spent {spent} but cap is {decimalize(budget_cap)}"
        )

    remaining = decimalize(budget_cap - spent)

    return SquadValidationSummary(
        spent=spent,
        remaining=remaining,
        position_counts={key: int(position_counts.get(key, 0)) for key in SQUAD_POSITION_LIMITS},
    )


def validate_matchday_picks(
    squad_player_ids: Set[int],
    player_positions: Mapping[int, str],
    picks: Sequence[Dict[str, Any]],
) -> Dict[str, Any]:
    if len(picks) != FANTASY_SQUAD_SIZE:
        raise FantasyRuleError("Matchday picks must include all 15 squad players")

    pick_player_ids = [int(item["player_id"]) for item in picks]
    if set(pick_player_ids) != squad_player_ids:
        raise FantasyRuleError("Matchday picks must reference only active squad players")

    starters = [item for item in picks if item.get("role") == "starter"]
    bench = [item for item in picks if item.get("role") == "bench"]

    if len(starters) != 11 or len(bench) != 4:
        raise FantasyRuleError("You must set exactly 11 starters and 4 bench players")

    bench_orders = [int(item.get("bench_order", 0)) for item in bench]
    if sorted(bench_orders) != [1, 2, 3, 4]:
        raise FantasyRuleError("Bench order must contain unique values from 1 to 4")

    captain_ids = [int(item["player_id"]) for item in picks if item.get("is_captain")]
    if len(captain_ids) != 1:
        raise FantasyRuleError("You must select exactly one captain")

    captain_id = captain_ids[0]
    if captain_id not in {int(item["player_id"]) for item in starters}:
        raise FantasyRuleError("Captain must be in the starting eleven")

    vice_ids = [int(item["player_id"]) for item in picks if item.get("is_vice_captain")]
    if len(vice_ids) > 1:
        raise FantasyRuleError("You can select at most one vice-captain")

    if vice_ids and vice_ids[0] == captain_id:
        raise FantasyRuleError("Captain and vice-captain must be different players")

    starter_position_counts = Counter(player_positions[int(item["player_id"])] for item in starters)

    for position_key, (min_allowed, max_allowed) in STARTING_POSITION_LIMITS.items():
        count = int(starter_position_counts.get(position_key, 0))
        if count < min_allowed or count > max_allowed:
            raise FantasyRuleError(
                f"Starting lineup must include {min_allowed}-{max_allowed} {position_key} players"
            )

    return {
        "captain_id": captain_id,
        "vice_captain_id": vice_ids[0] if vice_ids else None,
        "starter_ids": [int(item["player_id"]) for item in starters],
    }


def validate_transfer_batch(
    active_player_ids: Set[int],
    active_position_map: Mapping[int, str],
    active_team_map: Mapping[int, int],
    incoming_position_map: Mapping[int, str],
    incoming_team_map: Mapping[int, int],
    transfer_pairs: Sequence[Tuple[int, int]],
) -> None:
    out_ids = [out_player_id for out_player_id, _ in transfer_pairs]
    in_ids = [in_player_id for _, in_player_id in transfer_pairs]

    if len(out_ids) != len(set(out_ids)):
        raise FantasyRuleError("Each outgoing player can only be transferred once")

    if len(in_ids) != len(set(in_ids)):
        raise FantasyRuleError("Incoming players must be unique")

    for out_player_id, in_player_id in transfer_pairs:
        if out_player_id not in active_player_ids:
            raise FantasyRuleError(f"Outgoing player {out_player_id} is not in active squad")

        if in_player_id in active_player_ids:
            raise FantasyRuleError(f"Incoming player {in_player_id} is already in active squad")

        if active_position_map[out_player_id] != incoming_position_map[in_player_id]:
            raise FantasyRuleError("Transfers must preserve squad position structure")

    simulated_team_counts = Counter(active_team_map[player_id] for player_id in active_player_ids)

    for out_player_id, in_player_id in transfer_pairs:
        simulated_team_counts[active_team_map[out_player_id]] -= 1
        simulated_team_counts[incoming_team_map[in_player_id]] += 1

    if any(count > 3 for count in simulated_team_counts.values()):
        raise FantasyRuleError("Transfer would exceed 3-player-per-team rule")


def transfer_penalty(transfers_used: int) -> int:
    return max(0, transfers_used - FREE_TRANSFERS_PER_MATCHDAY) * EXTRA_TRANSFER_PENALTY


def _normalize_event_type(event_type: Optional[str]) -> str:
    event = _normalize_text(event_type)
    if "goal" in event:
        return "goal"
    if "assist" in event:
        return "assist"
    if "card" in event:
        return "card"
    return "other"


def _player_name_matches(event_player_name: Optional[str], target_name: Optional[str]) -> bool:
    event_name = _normalize_text(event_player_name)
    target = _normalize_text(target_name)

    if not event_name or not target:
        return False

    return event_name == target or event_name in target or target in event_name


def _event_points(position_key: str, event_type: str, detail: Optional[str]) -> int:
    normalized_event = _normalize_event_type(event_type)
    detail_normalized = _normalize_text(detail)

    if normalized_event == "goal":
        points = GOAL_POINTS_BY_POSITION.get(position_key, 4)
        if "own" in detail_normalized:
            points -= 2
        return points

    if normalized_event == "assist":
        return 3

    if normalized_event == "card":
        if "red" in detail_normalized:
            return -3
        return -1

    return 0


def compute_matchday_points(
    starters: Sequence[Dict[str, Any]],
    captain_player_id: Optional[int],
    finished_matches: Sequence[Match],
    events_by_match: Mapping[int, Sequence[MatchEvent]],
) -> Tuple[int, List[Dict[str, Any]]]:
    points_by_player: Dict[int, int] = defaultdict(int)
    entries: List[Dict[str, Any]] = []

    starters_by_team: Dict[int, List[Dict[str, Any]]] = defaultdict(list)
    starters_by_id: Dict[int, Dict[str, Any]] = {}

    for starter in starters:
        starter_id = int(starter["player_id"])
        team_id = int(starter["team_id"])
        starters_by_team[team_id].append(starter)
        starters_by_id[starter_id] = starter

    team_match_map: Dict[int, Match] = {}
    for match in finished_matches:
        team_match_map[match.home_team_id] = match
        team_match_map[match.away_team_id] = match

    for starter in starters:
        player_id = int(starter["player_id"])
        team_id = int(starter["team_id"])

        if team_id in team_match_map:
            points_by_player[player_id] += 2
            entries.append(
                {
                    "player_id": player_id,
                    "match_id": team_match_map[team_id].id,
                    "points": 2,
                    "reason": "appearance",
                }
            )

    for match in finished_matches:
        match_events = events_by_match.get(match.id, [])

        for event in match_events:
            team_starters = starters_by_team.get(event.team_id, [])
            if not team_starters:
                continue

            for starter in team_starters:
                if not _player_name_matches(event.player_name, starter.get("player_name")):
                    continue

                player_id = int(starter["player_id"])
                position_key = str(starter["position_key"])
                delta = _event_points(position_key, event.event_type, event.detail)

                if delta == 0:
                    continue

                points_by_player[player_id] += delta
                entries.append(
                    {
                        "player_id": player_id,
                        "match_id": match.id,
                        "points": delta,
                        "reason": _normalize_event_type(event.event_type),
                    }
                )

    for starter in starters:
        player_id = int(starter["player_id"])
        team_id = int(starter["team_id"])
        position_key = str(starter["position_key"])

        match = team_match_map.get(team_id)
        if not match:
            continue

        conceded = match.away_score if match.home_team_id == team_id else match.home_score
        if conceded != 0:
            continue

        clean_sheet_points = CLEAN_SHEET_POINTS_BY_POSITION.get(position_key, 0)
        if clean_sheet_points <= 0:
            continue

        points_by_player[player_id] += clean_sheet_points
        entries.append(
            {
                "player_id": player_id,
                "match_id": match.id,
                "points": clean_sheet_points,
                "reason": "clean_sheet",
            }
        )

    if captain_player_id is not None and captain_player_id in points_by_player:
        captain_bonus = points_by_player[captain_player_id]
        if captain_bonus != 0:
            points_by_player[captain_player_id] += captain_bonus
            captain_match = team_match_map.get(starters_by_id[captain_player_id]["team_id"])
            entries.append(
                {
                    "player_id": captain_player_id,
                    "match_id": captain_match.id if captain_match else None,
                    "points": captain_bonus,
                    "reason": "captain_multiplier",
                }
            )

    total_points = sum(points_by_player.values())
    return int(total_points), entries


def filter_supported_players(db: Session, player_ids: Iterable[int]) -> List[Player]:
    ids = list({int(player_id) for player_id in player_ids})
    if not ids:
        return []

    players = db.query(Player).filter(Player.id.in_(ids)).all()

    supported_players: List[Player] = []
    for player in players:
        team = db.query(Team).filter(Team.id == player.team_id).first()
        league = db.query(League).filter(League.id == team.league_id).first() if team else None

        if is_player_supported_scope(player, team, league):
            supported_players.append(player)

    return supported_players
