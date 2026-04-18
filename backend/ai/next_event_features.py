import datetime
from collections import defaultdict
from typing import Dict, List, Optional, Sequence, Tuple

import numpy as np
import pandas as pd
from sqlalchemy import or_
from sqlalchemy.orm import Session

try:
    from backend.models import League, Match, MatchEvent, Player, Standing, Team
    from backend.ai.next_event_common import (
        FINISHED_MATCH_STATUSES,
        extract_assist_name,
        extract_sub_out_name,
        is_card_event,
        is_goal_event,
        is_red_card_detail,
        is_substitution_event,
        is_supported_league,
        normalize_text,
    )
except ImportError:
    from models import League, Match, MatchEvent, Player, Standing, Team
    from ai.next_event_common import (
        FINISHED_MATCH_STATUSES,
        extract_assist_name,
        extract_sub_out_name,
        is_card_event,
        is_goal_event,
        is_red_card_detail,
        is_substitution_event,
        is_supported_league,
        normalize_text,
    )


LIVE_MATCH_STATUSES = {"1H", "2H", "ET", "LIVE", "HT"}

FEATURE_COLUMNS = [
    "minute_norm",
    "is_home",
    "team_trailing",
    "team_leading",
    "goal_diff",
    "team_red_cards",
    "opp_red_cards",
    "team_yellow_cards",
    "player_yellow_cards",
    "player_red_cards",
    "is_probable_starter",
    "is_on_pitch",
    "player_minutes_norm",
    "player_goals_per90",
    "player_assists_per90",
    "player_goal_involvement_per90",
    "player_rating_norm",
    "player_recent_goals_last5",
    "player_recent_assists_last5",
    "player_recent_involvement_last5",
    "team_attack_prior",
    "team_defense_prior",
    "opp_defense_prior",
    "team_points_per_match",
    "opp_points_per_match",
    "team_goal_diff_per_match",
    "opp_goal_diff_per_match",
    "position_attacker",
    "position_midfielder",
    "position_defender",
    "position_goalkeeper",
]

TRAINING_COLUMNS = [
    "sample_id",
    "match_id",
    "event_id",
    "event_minute",
    "event_time",
    "player_id",
    "player_name",
    "team_id",
    "label",
    *FEATURE_COLUMNS,
]


def _safe_float(value: Optional[float], default: float = 0.0) -> float:
    if value is None:
        return default
    try:
        return float(value)
    except (TypeError, ValueError):
        return default


def _safe_int(value: Optional[int], default: int = 0) -> int:
    if value is None:
        return default
    try:
        return int(float(value))
    except (TypeError, ValueError):
        return default


def _clamp(value: float, low: float, high: float) -> float:
    return max(low, min(high, value))


def _per90(metric: float, minutes: float) -> float:
    if minutes <= 0:
        return 0.0
    return (metric / minutes) * 90.0


def _resolve_position_flags(position: Optional[str]) -> Dict[str, float]:
    normalized = normalize_text(position)
    if "forward" in normalized or "striker" in normalized or "attacker" in normalized or "wing" in normalized:
        return {
            "position_attacker": 1.0,
            "position_midfielder": 0.0,
            "position_defender": 0.0,
            "position_goalkeeper": 0.0,
        }

    if "midfield" in normalized:
        return {
            "position_attacker": 0.0,
            "position_midfielder": 1.0,
            "position_defender": 0.0,
            "position_goalkeeper": 0.0,
        }

    if "defen" in normalized or "back" in normalized:
        return {
            "position_attacker": 0.0,
            "position_midfielder": 0.0,
            "position_defender": 1.0,
            "position_goalkeeper": 0.0,
        }

    if "goalkeeper" in normalized or normalized == "gk" or "keeper" in normalized:
        return {
            "position_attacker": 0.0,
            "position_midfielder": 0.0,
            "position_defender": 0.0,
            "position_goalkeeper": 1.0,
        }

    return {
        "position_attacker": 0.0,
        "position_midfielder": 0.0,
        "position_defender": 0.0,
        "position_goalkeeper": 0.0,
    }


def _match_player_name(event_player_name: Optional[str], player_name: Optional[str]) -> bool:
    event_name = normalize_text(event_player_name)
    target_name = normalize_text(player_name)

    if not event_name or not target_name:
        return False

    if event_name == target_name:
        return True

    if event_name in target_name or target_name in event_name:
        return True

    event_tokens = [token for token in event_name.replace(".", " ").split(" ") if token]
    target_tokens = [token for token in target_name.replace(".", " ").split(" ") if token]

    if not event_tokens or not target_tokens:
        return False

    overlap = len(set(event_tokens) & set(target_tokens))
    return overlap >= min(len(event_tokens), len(target_tokens), 2)


class NextEventFeatureBuilder:
    def __init__(self, db: Session):
        self.db = db
        self._team_cache: Dict[int, Optional[Team]] = {}
        self._league_cache: Dict[int, Optional[League]] = {}
        self._players_by_team_cache: Dict[int, List[Player]] = {}
        self._events_by_match_cache: Dict[int, List[MatchEvent]] = {}
        self._probable_lineup_cache: Dict[int, List[int]] = {}
        self._team_prior_cache: Dict[Tuple[int, str], Dict[str, float]] = {}
        self._player_recent_form_cache: Dict[Tuple[int, str], Dict[str, float]] = {}

    def _team(self, team_id: int) -> Optional[Team]:
        if team_id not in self._team_cache:
            self._team_cache[team_id] = self.db.query(Team).filter(Team.id == team_id).first()
        return self._team_cache[team_id]

    def _league_for_team(self, team_id: int) -> Optional[League]:
        team = self._team(team_id)
        if not team or not team.league_id:
            return None

        if team.league_id not in self._league_cache:
            self._league_cache[team.league_id] = self.db.query(League).filter(League.id == team.league_id).first()

        return self._league_cache[team.league_id]

    def is_supported_match(self, match: Match) -> bool:
        home_league = self._league_for_team(match.home_team_id)
        away_league = self._league_for_team(match.away_team_id)
        return bool(is_supported_league(home_league) or is_supported_league(away_league))

    def get_supported_finished_matches(self) -> List[Match]:
        raw_matches = (
            self.db.query(Match)
            .filter(
                Match.status.in_(list(FINISHED_MATCH_STATUSES)),
                Match.home_score.isnot(None),
                Match.away_score.isnot(None),
            )
            .order_by(Match.start_time.asc(), Match.id.asc())
            .all()
        )
        return [match for match in raw_matches if self.is_supported_match(match)]

    def _events_for_match(self, match_id: int) -> List[MatchEvent]:
        if match_id not in self._events_by_match_cache:
            self._events_by_match_cache[match_id] = (
                self.db.query(MatchEvent)
                .filter(MatchEvent.match_id == match_id)
                .order_by(MatchEvent.minute.asc(), MatchEvent.id.asc())
                .all()
            )
        return self._events_by_match_cache[match_id]

    def _players_for_team(self, team_id: int) -> List[Player]:
        if team_id not in self._players_by_team_cache:
            players = self.db.query(Player).filter(Player.team_id == team_id).all()
            players = sorted(
                players,
                key=lambda player: (
                    _safe_int(player.minutes_played),
                    _safe_float(player.rating_season),
                    _safe_float(player.goals_season),
                    _safe_float(player.assists_season),
                    player.name or "",
                ),
                reverse=True,
            )
            self._players_by_team_cache[team_id] = players
        return self._players_by_team_cache[team_id]

    def _resolve_player_by_name(self, player_name: Optional[str], players: Sequence[Player]) -> Optional[Player]:
        if not player_name:
            return None

        for player in players:
            if _match_player_name(player_name, player.name):
                return player

        return None

    def _probable_lineup_ids(self, team_id: int) -> List[int]:
        if team_id not in self._probable_lineup_cache:
            players = self._players_for_team(team_id)
            probable = [player.id for player in players[:11]]
            self._probable_lineup_cache[team_id] = probable
        return self._probable_lineup_cache[team_id]

    def _team_prior(self, team_id: int, cutoff_time: datetime.datetime) -> Dict[str, float]:
        cache_key = (team_id, cutoff_time.date().isoformat())
        if cache_key in self._team_prior_cache:
            return self._team_prior_cache[cache_key]

        recent_matches = (
            self.db.query(Match)
            .filter(
                Match.status.in_(list(FINISHED_MATCH_STATUSES)),
                Match.home_score.isnot(None),
                Match.away_score.isnot(None),
                Match.start_time < cutoff_time,
                or_(Match.home_team_id == team_id, Match.away_team_id == team_id),
            )
            .order_by(Match.start_time.desc())
            .limit(15)
            .all()
        )

        matches_count = len(recent_matches)
        goals_for = 0.0
        goals_against = 0.0
        points = 0.0

        for row in recent_matches:
            if row.home_team_id == team_id:
                team_goals = _safe_float(row.home_score)
                opp_goals = _safe_float(row.away_score)
            else:
                team_goals = _safe_float(row.away_score)
                opp_goals = _safe_float(row.home_score)

            goals_for += team_goals
            goals_against += opp_goals

            if team_goals > opp_goals:
                points += 3.0
            elif team_goals == opp_goals:
                points += 1.0

        standing = self.db.query(Standing).filter(Standing.team_id == team_id).first()

        if matches_count > 0:
            attack_prior = goals_for / matches_count
            defense_prior = goals_against / matches_count
            points_per_match = points / matches_count
            goal_diff_per_match = (goals_for - goals_against) / matches_count
        elif standing and _safe_int(standing.played) > 0:
            played = _safe_float(standing.played)
            attack_prior = _safe_float(standing.goals_for) / played
            defense_prior = _safe_float(standing.goals_against) / played
            points_per_match = _safe_float(standing.points) / played
            goal_diff_per_match = _safe_float(standing.goal_difference) / played
        else:
            attack_prior = 1.2
            defense_prior = 1.2
            points_per_match = 1.2
            goal_diff_per_match = 0.0

        payload = {
            "attack_prior": round(max(0.1, attack_prior), 4),
            "defense_prior": round(max(0.1, defense_prior), 4),
            "points_per_match": round(max(0.1, points_per_match), 4),
            "goal_diff_per_match": round(goal_diff_per_match, 4),
        }
        self._team_prior_cache[cache_key] = payload
        return payload

    def _player_recent_form(self, player: Player, cutoff_time: datetime.datetime) -> Dict[str, float]:
        cache_key = (player.id, cutoff_time.date().isoformat())
        if cache_key in self._player_recent_form_cache:
            return self._player_recent_form_cache[cache_key]

        recent_matches = (
            self.db.query(Match)
            .filter(
                Match.status.in_(list(FINISHED_MATCH_STATUSES)),
                Match.start_time < cutoff_time,
                or_(Match.home_team_id == player.team_id, Match.away_team_id == player.team_id),
            )
            .order_by(Match.start_time.desc())
            .limit(20)
            .all()
        )

        goals_last5 = 0
        assists_last5 = 0
        matches_counted = 0

        if recent_matches:
            match_ids = [row.id for row in recent_matches]
            all_events = (
                self.db.query(MatchEvent)
                .filter(MatchEvent.match_id.in_(match_ids))
                .order_by(MatchEvent.match_id.asc(), MatchEvent.minute.asc(), MatchEvent.id.asc())
                .all()
            )

            events_by_match: Dict[int, List[MatchEvent]] = defaultdict(list)
            for event in all_events:
                events_by_match[event.match_id].append(event)

            for row in recent_matches:
                matches_counted += 1
                for event in events_by_match.get(row.id, []):
                    if is_goal_event(event.event_type) and _match_player_name(event.player_name, player.name):
                        goals_last5 += 1

                    if _match_player_name(extract_assist_name(event.detail), player.name):
                        assists_last5 += 1
                    elif "assist" in normalize_text(event.event_type) and _match_player_name(event.player_name, player.name):
                        assists_last5 += 1

                if matches_counted >= 5:
                    break

        payload = {
            "goals_last5": float(goals_last5),
            "assists_last5": float(assists_last5),
            "involvement_last5": float(goals_last5 + assists_last5),
        }
        self._player_recent_form_cache[cache_key] = payload
        return payload

    def _on_pitch_ids(
        self,
        match: Match,
        team_id: int,
        events: Sequence[MatchEvent],
        cutoff_minute: int,
        team_players: Sequence[Player],
    ) -> List[int]:
        player_map = {player.id: player for player in team_players}
        probable_lineup = list(self._probable_lineup_ids(team_id))
        on_pitch = set(player_id for player_id in probable_lineup if player_id in player_map)

        if not on_pitch:
            on_pitch = set(player_map.keys())

        for event in events:
            minute = _safe_int(event.minute)
            if minute > cutoff_minute:
                break
            if event.team_id != team_id:
                continue
            if not is_substitution_event(event.event_type):
                continue

            incoming = self._resolve_player_by_name(event.player_name, team_players)
            outgoing_name = extract_sub_out_name(event.detail)
            outgoing = self._resolve_player_by_name(outgoing_name, team_players)

            if outgoing:
                on_pitch.discard(outgoing.id)
            if incoming:
                on_pitch.add(incoming.id)

        if len(on_pitch) < 8:
            for player_id in probable_lineup:
                on_pitch.add(player_id)
                if len(on_pitch) >= 11:
                    break

        return sorted(on_pitch)

    def _build_match_state(
        self,
        match: Match,
        events: Sequence[MatchEvent],
        cutoff_minute: int,
        home_players: Sequence[Player],
        away_players: Sequence[Player],
    ) -> Dict[str, object]:
        home_goals = 0
        away_goals = 0

        team_yellow: Dict[int, int] = defaultdict(int)
        team_red: Dict[int, int] = defaultdict(int)
        player_yellow: Dict[int, int] = defaultdict(int)
        player_red: Dict[int, int] = defaultdict(int)

        home_team_players = [player for player in home_players if player.team_id == match.home_team_id]
        away_team_players = [player for player in away_players if player.team_id == match.away_team_id]

        for event in events:
            minute = _safe_int(event.minute)
            if minute > cutoff_minute:
                break

            if is_goal_event(event.event_type):
                if event.team_id == match.home_team_id:
                    home_goals += 1
                elif event.team_id == match.away_team_id:
                    away_goals += 1

            if is_card_event(event.event_type):
                if event.team_id is not None:
                    if is_red_card_detail(event.detail):
                        team_red[event.team_id] += 1
                    else:
                        team_yellow[event.team_id] += 1

                team_players = home_team_players if event.team_id == match.home_team_id else away_team_players
                player = self._resolve_player_by_name(event.player_name, team_players)
                if player:
                    if is_red_card_detail(event.detail):
                        player_red[player.id] += 1
                    else:
                        player_yellow[player.id] += 1

        return {
            "home_goals": home_goals,
            "away_goals": away_goals,
            "team_yellow": team_yellow,
            "team_red": team_red,
            "player_yellow": player_yellow,
            "player_red": player_red,
        }

    def _candidate_feature_row(
        self,
        match: Match,
        player: Player,
        is_on_pitch: bool,
        is_probable_starter: bool,
        minute: int,
        match_state: Dict[str, object],
    ) -> Dict[str, float]:
        is_home = player.team_id == match.home_team_id
        opponent_team_id = match.away_team_id if is_home else match.home_team_id

        team_score = match_state["home_goals"] if is_home else match_state["away_goals"]
        opponent_score = match_state["away_goals"] if is_home else match_state["home_goals"]
        goal_diff = float(team_score - opponent_score)

        team_yellow = _safe_float(match_state["team_yellow"].get(player.team_id, 0))
        team_red = _safe_float(match_state["team_red"].get(player.team_id, 0))
        opp_red = _safe_float(match_state["team_red"].get(opponent_team_id, 0))
        player_yellow = _safe_float(match_state["player_yellow"].get(player.id, 0))
        player_red = _safe_float(match_state["player_red"].get(player.id, 0))

        player_minutes = _safe_float(player.minutes_played)
        player_goals = _safe_float(player.goals_season)
        player_assists = _safe_float(player.assists_season)
        player_rating = _safe_float(player.rating_season)

        player_recent = self._player_recent_form(player, match.start_time)
        team_prior = self._team_prior(player.team_id, match.start_time)
        opp_prior = self._team_prior(opponent_team_id, match.start_time)

        position_flags = _resolve_position_flags(player.position)

        row = {
            "minute_norm": _clamp(minute / 95.0, 0.0, 1.0),
            "is_home": 1.0 if is_home else 0.0,
            "team_trailing": 1.0 if goal_diff < 0 else 0.0,
            "team_leading": 1.0 if goal_diff > 0 else 0.0,
            "goal_diff": goal_diff,
            "team_red_cards": team_red,
            "opp_red_cards": opp_red,
            "team_yellow_cards": team_yellow,
            "player_yellow_cards": player_yellow,
            "player_red_cards": player_red,
            "is_probable_starter": 1.0 if is_probable_starter else 0.0,
            "is_on_pitch": 1.0 if is_on_pitch else 0.0,
            "player_minutes_norm": _clamp(player_minutes / 3000.0, 0.0, 1.5),
            "player_goals_per90": _per90(player_goals, player_minutes),
            "player_assists_per90": _per90(player_assists, player_minutes),
            "player_goal_involvement_per90": _per90(player_goals + player_assists, player_minutes),
            "player_rating_norm": _clamp(player_rating / 10.0, 0.0, 1.0),
            "player_recent_goals_last5": player_recent["goals_last5"],
            "player_recent_assists_last5": player_recent["assists_last5"],
            "player_recent_involvement_last5": player_recent["involvement_last5"],
            "team_attack_prior": team_prior["attack_prior"],
            "team_defense_prior": team_prior["defense_prior"],
            "opp_defense_prior": opp_prior["defense_prior"],
            "team_points_per_match": team_prior["points_per_match"],
            "opp_points_per_match": opp_prior["points_per_match"],
            "team_goal_diff_per_match": team_prior["goal_diff_per_match"],
            "opp_goal_diff_per_match": opp_prior["goal_diff_per_match"],
            **position_flags,
        }
        return row

    def build_training_frame(self, task: str, min_candidates: int = 8) -> pd.DataFrame:
        task_normalized = normalize_text(task)
        if task_normalized not in {"goal", "assist"}:
            raise ValueError("task must be either 'goal' or 'assist'")

        rows: List[Dict[str, object]] = []
        matches = self.get_supported_finished_matches()

        for match in matches:
            events = self._events_for_match(match.id)
            goal_events = [
                event
                for event in events
                if is_goal_event(event.event_type)
                and event.team_id in {match.home_team_id, match.away_team_id}
                and _safe_int(event.minute) > 0
            ]
            if not goal_events:
                continue

            home_players = self._players_for_team(match.home_team_id)
            away_players = self._players_for_team(match.away_team_id)
            if not home_players or not away_players:
                continue

            combined_players = home_players + away_players
            on_pitch_cache: Dict[Tuple[int, int], List[int]] = {}
            probable_home = set(self._probable_lineup_ids(match.home_team_id))
            probable_away = set(self._probable_lineup_ids(match.away_team_id))

            for goal_event in goal_events:
                minute = max(1, _safe_int(goal_event.minute))
                context_minute = max(0, minute - 1)

                if task_normalized == "goal":
                    target_name = goal_event.player_name
                else:
                    target_name = extract_assist_name(goal_event.detail)

                if not target_name:
                    continue

                if (match.home_team_id, context_minute) not in on_pitch_cache:
                    on_pitch_cache[(match.home_team_id, context_minute)] = self._on_pitch_ids(
                        match,
                        match.home_team_id,
                        events,
                        context_minute,
                        home_players,
                    )

                if (match.away_team_id, context_minute) not in on_pitch_cache:
                    on_pitch_cache[(match.away_team_id, context_minute)] = self._on_pitch_ids(
                        match,
                        match.away_team_id,
                        events,
                        context_minute,
                        away_players,
                    )

                home_on_pitch = set(on_pitch_cache[(match.home_team_id, context_minute)])
                away_on_pitch = set(on_pitch_cache[(match.away_team_id, context_minute)])

                candidate_players = [
                    player
                    for player in combined_players
                    if (player.team_id == match.home_team_id and player.id in home_on_pitch)
                    or (player.team_id == match.away_team_id and player.id in away_on_pitch)
                ]

                if len(candidate_players) < min_candidates:
                    continue

                target_player = self._resolve_player_by_name(target_name, candidate_players)
                if not target_player:
                    continue

                state = self._build_match_state(
                    match,
                    events,
                    context_minute,
                    home_players,
                    away_players,
                )

                sample_id = f"{task_normalized}:{match.id}:{goal_event.id}"
                event_time = match.start_time + datetime.timedelta(minutes=minute)

                for candidate in candidate_players:
                    is_home = candidate.team_id == match.home_team_id
                    probable_lineup = probable_home if is_home else probable_away
                    on_pitch_ids = home_on_pitch if is_home else away_on_pitch

                    feature_row = self._candidate_feature_row(
                        match=match,
                        player=candidate,
                        is_on_pitch=candidate.id in on_pitch_ids,
                        is_probable_starter=candidate.id in probable_lineup,
                        minute=minute,
                        match_state=state,
                    )

                    row = {
                        "sample_id": sample_id,
                        "match_id": match.id,
                        "event_id": goal_event.id,
                        "event_minute": minute,
                        "event_time": event_time,
                        "player_id": candidate.id,
                        "player_name": candidate.name,
                        "team_id": candidate.team_id,
                        "label": 1 if candidate.id == target_player.id else 0,
                        **feature_row,
                    }
                    rows.append(row)

        if not rows:
            return pd.DataFrame(columns=TRAINING_COLUMNS)

        frame = pd.DataFrame(rows)
        for column in FEATURE_COLUMNS:
            frame[column] = frame[column].astype(float)

        return frame[TRAINING_COLUMNS]

    def _infer_live_minute(self, match: Match, events: Sequence[MatchEvent], minute_override: Optional[int]) -> int:
        if minute_override is not None:
            return max(1, _safe_int(minute_override, default=1))

        if events:
            latest = max(_safe_int(event.minute, default=0) for event in events)
            return max(1, latest)

        if normalize_text(match.status) in {normalize_text(status) for status in LIVE_MATCH_STATUSES}:
            return 45

        return 1

    def build_live_candidate_frame(self, match: Match, minute_override: Optional[int] = None) -> Tuple[pd.DataFrame, Dict[str, object]]:
        events = self._events_for_match(match.id)
        minute = self._infer_live_minute(match, events, minute_override)

        home_players = self._players_for_team(match.home_team_id)
        away_players = self._players_for_team(match.away_team_id)
        combined_players = home_players + away_players

        if not combined_players:
            return pd.DataFrame(), {
                "minute": minute,
                "candidate_count": 0,
                "missing_player_stats": 0,
                "events_seen": len(events),
            }

        home_on_pitch = set(self._on_pitch_ids(match, match.home_team_id, events, minute, home_players))
        away_on_pitch = set(self._on_pitch_ids(match, match.away_team_id, events, minute, away_players))

        probable_home = set(self._probable_lineup_ids(match.home_team_id))
        probable_away = set(self._probable_lineup_ids(match.away_team_id))

        state = self._build_match_state(match, events, minute, home_players, away_players)

        candidate_rows: List[Dict[str, object]] = []
        missing_stats_count = 0

        for candidate in combined_players:
            is_home = candidate.team_id == match.home_team_id
            on_pitch_ids = home_on_pitch if is_home else away_on_pitch
            probable_ids = probable_home if is_home else probable_away

            if candidate.id not in on_pitch_ids:
                continue

            if (
                candidate.minutes_played is None
                and candidate.goals_season is None
                and candidate.assists_season is None
                and candidate.rating_season is None
            ):
                missing_stats_count += 1

            feature_row = self._candidate_feature_row(
                match=match,
                player=candidate,
                is_on_pitch=True,
                is_probable_starter=candidate.id in probable_ids,
                minute=minute,
                match_state=state,
            )

            candidate_rows.append(
                {
                    "player_id": candidate.id,
                    "player_name": candidate.name,
                    "team_id": candidate.team_id,
                    "team_name": self._team(candidate.team_id).name if self._team(candidate.team_id) else "Unknown",
                    "event_minute": minute,
                    **feature_row,
                }
            )

        if not candidate_rows:
            return pd.DataFrame(), {
                "minute": minute,
                "candidate_count": 0,
                "missing_player_stats": missing_stats_count,
                "events_seen": len(events),
            }

        frame = pd.DataFrame(candidate_rows)
        for column in FEATURE_COLUMNS:
            frame[column] = frame[column].astype(float)

        context = {
            "minute": minute,
            "candidate_count": len(frame),
            "missing_player_stats": missing_stats_count,
            "events_seen": len(events),
            "home_score_inferred": state["home_goals"],
            "away_score_inferred": state["away_goals"],
        }
        return frame, context
