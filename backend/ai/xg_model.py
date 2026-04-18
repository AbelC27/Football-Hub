import datetime
import math
import pickle
import random
from dataclasses import dataclass, asdict
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

import numpy as np
import pandas as pd
from sklearn.linear_model import LogisticRegression, PoissonRegressor
from sklearn.metrics import mean_absolute_error, mean_squared_error, r2_score
from sklearn.model_selection import train_test_split
from sklearn.pipeline import Pipeline
from sklearn.preprocessing import StandardScaler
from sqlalchemy import inspect, or_, text
from sqlalchemy.orm import Session

try:
    from backend.models import League, Match, MatchEvent, MatchStatistics, Team
    from backend.ai.next_event_common import is_card_event, is_goal_event, is_red_card_detail, is_supported_league, normalize_text
    from backend.ai.xg_common import (
        OPTIONAL_TRUE_XG_COLUMNS,
        REQUIRED_TRUE_XG_COLUMNS,
        XG_SCOPE,
        XGGranularity,
        detect_xg_granularity,
    )
except ImportError:
    from models import League, Match, MatchEvent, MatchStatistics, Team
    from ai.next_event_common import is_card_event, is_goal_event, is_red_card_detail, is_supported_league, normalize_text
    from ai.xg_common import (
        OPTIONAL_TRUE_XG_COLUMNS,
        REQUIRED_TRUE_XG_COLUMNS,
        XG_SCOPE,
        XGGranularity,
        detect_xg_granularity,
    )


ARTIFACT_DIR = Path(__file__).resolve().parent / "artifacts"
DEFAULT_XG_ARTIFACT_PATH = ARTIFACT_DIR / "xg_model.pkl"
DEFAULT_XG_METRICS_PATH = ARTIFACT_DIR / "xg_training_metrics.json"
DEFAULT_XG_CONFIG_PATH = ARTIFACT_DIR / "xg_training_config.json"
DEFAULT_XG_FEATURE_DOC_PATH = ARTIFACT_DIR / "xg_feature_docs.md"

LIVE_MATCH_STATUSES = {"LIVE", "HT", "1H", "2H", "ET", "P"}
FINISHED_MATCH_STATUSES = {"FT", "AET", "PEN"}

PROXY_FEATURE_COLUMNS = [
    "is_home",
    "team_points_per_match",
    "team_goals_for_avg",
    "team_goals_against_avg",
    "team_shots_on_avg",
    "team_shots_off_avg",
    "team_possession_avg",
    "team_corners_avg",
    "team_form_points_last5",
    "team_rest_days",
    "opp_points_per_match",
    "opp_goals_for_avg",
    "opp_goals_against_avg",
    "opp_shots_on_avg",
    "opp_shots_off_avg",
    "opp_possession_avg",
    "opp_corners_avg",
    "opp_form_points_last5",
    "opp_rest_days",
    "is_ucl_match",
    "team_stats_coverage",
    "opp_stats_coverage",
]

PROXY_FEATURE_DOCS = {
    "is_home": "1 if perspective team is home, else 0.",
    "team_points_per_match": "Team average league points per match from recent supported history.",
    "team_goals_for_avg": "Team average goals scored per match over recent supported history.",
    "team_goals_against_avg": "Team average goals conceded per match over recent supported history.",
    "team_shots_on_avg": "Team average shots on target from available aggregate match statistics.",
    "team_shots_off_avg": "Team average shots off target from available aggregate match statistics.",
    "team_possession_avg": "Team average possession percentage from available aggregate match statistics.",
    "team_corners_avg": "Team average corners from available aggregate match statistics.",
    "team_form_points_last5": "Team points collected in the last five supported finished matches.",
    "team_rest_days": "Days since team last supported finished match before kickoff.",
    "opp_points_per_match": "Opponent average points per match from recent supported history.",
    "opp_goals_for_avg": "Opponent average goals scored per match over recent supported history.",
    "opp_goals_against_avg": "Opponent average goals conceded per match over recent supported history.",
    "opp_shots_on_avg": "Opponent average shots on target from available aggregate match statistics.",
    "opp_shots_off_avg": "Opponent average shots off target from available aggregate match statistics.",
    "opp_possession_avg": "Opponent average possession percentage from available aggregate match statistics.",
    "opp_corners_avg": "Opponent average corners from available aggregate match statistics.",
    "opp_form_points_last5": "Opponent points in last five supported finished matches.",
    "opp_rest_days": "Days since opponent last supported finished match before kickoff.",
    "is_ucl_match": "1 when competition name indicates Champions League context, else 0.",
    "team_stats_coverage": "Share of history matches where aggregate stats were available for the perspective team.",
    "opp_stats_coverage": "Share of history matches where aggregate stats were available for the opponent.",
}

TRUE_SHOT_FEATURE_COLUMNS = [
    "shot_distance",
    "shot_angle",
    "is_header",
    "is_set_piece",
    "assist_cross",
    "under_pressure_flag",
]

TRUE_SHOT_FEATURE_DOCS = {
    "shot_distance": "Approximate distance to goal from normalized shot coordinates.",
    "shot_angle": "Approximate centrality angle derived from normalized shot coordinates.",
    "is_header": "1 when shot/body-part text suggests a header.",
    "is_set_piece": "1 when shot-type indicates penalty/free-kick/set-play.",
    "assist_cross": "1 when assist-type indicates cross/set-piece delivery.",
    "under_pressure_flag": "1 when provider marks shot as taken under defensive pressure.",
}


@dataclass
class XGTrainingConfig:
    seed: int = 42
    test_ratio: float = 0.2
    history_window: int = 12
    min_training_rows: int = 120
    shot_min_rows: int = 300
    poisson_alpha: float = 0.18

    def to_dict(self) -> Dict[str, Any]:
        return asdict(self)


def _utc_now_iso() -> str:
    return datetime.datetime.utcnow().replace(microsecond=0).isoformat() + "Z"


def _safe_float(value: Any, default: float = 0.0) -> float:
    if value is None:
        return default
    try:
        return float(value)
    except (TypeError, ValueError):
        return default


def _safe_int(value: Any, default: int = 0) -> int:
    if value is None:
        return default
    try:
        return int(float(value))
    except (TypeError, ValueError):
        return default


def _clamp(value: float, low: float, high: float) -> float:
    return max(low, min(high, value))


def _is_ucl_name(value: Optional[str]) -> bool:
    return "champions league" in normalize_text(value)


def _expected_calibration_error(probabilities: np.ndarray, labels: np.ndarray, bins: int = 10) -> float:
    if probabilities.size == 0:
        return 0.0

    edges = np.linspace(0.0, 1.0, bins + 1)
    ece = 0.0

    for index in range(bins):
        left = edges[index]
        right = edges[index + 1]

        if index == bins - 1:
            mask = (probabilities >= left) & (probabilities <= right)
        else:
            mask = (probabilities >= left) & (probabilities < right)

        if not np.any(mask):
            continue

        conf = float(np.mean(probabilities[mask]))
        acc = float(np.mean(labels[mask]))
        weight = float(np.mean(mask.astype(np.float64)))
        ece += abs(conf - acc) * weight

    return float(ece)


def _regression_calibration_bins(
    y_pred: np.ndarray,
    y_true: np.ndarray,
    bins: int = 10,
) -> Tuple[List[Dict[str, Any]], float]:
    if y_pred.size == 0:
        return [], 0.0

    bins = max(2, min(bins, len(y_pred)))
    edges = np.quantile(y_pred, q=np.linspace(0.0, 1.0, bins + 1))
    edges = np.unique(edges)

    if len(edges) < 2:
        edges = np.array([float(np.min(y_pred)), float(np.max(y_pred)) + 1e-6], dtype=np.float64)

    calibration_rows: List[Dict[str, Any]] = []
    abs_sum = 0.0
    total = len(y_pred)

    for idx in range(len(edges) - 1):
        left = float(edges[idx])
        right = float(edges[idx + 1])

        if idx == len(edges) - 2:
            mask = (y_pred >= left) & (y_pred <= right)
        else:
            mask = (y_pred >= left) & (y_pred < right)

        count = int(np.sum(mask))
        if count == 0:
            continue

        pred_mean = float(np.mean(y_pred[mask]))
        true_mean = float(np.mean(y_true[mask]))
        abs_diff = abs(pred_mean - true_mean)

        calibration_rows.append(
            {
                "bin_start": round(left, 4),
                "bin_end": round(right, 4),
                "count": count,
                "predicted_mean": round(pred_mean, 4),
                "actual_mean": round(true_mean, 4),
                "absolute_gap": round(abs_diff, 4),
            }
        )

        abs_sum += abs_diff * count

    calibration_mae = float(abs_sum / max(1, total))
    return calibration_rows, calibration_mae


def _serialize(obj: Any) -> Any:
    if isinstance(obj, dict):
        return {key: _serialize(value) for key, value in obj.items()}
    if isinstance(obj, list):
        return [_serialize(value) for value in obj]
    if hasattr(obj, "item"):
        return obj.item()
    return obj


class XGFeatureBuilder:
    def __init__(self, db: Session):
        self.db = db
        self._team_cache: Dict[int, Optional[Team]] = {}
        self._league_cache: Dict[int, Optional[League]] = {}
        self._stats_cache: Dict[int, Optional[MatchStatistics]] = {}
        self._events_cache: Dict[int, List[MatchEvent]] = {}

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

    def supported_finished_matches(self) -> List[Match]:
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

    def stats_for_match(self, match_id: int) -> Optional[MatchStatistics]:
        if match_id not in self._stats_cache:
            self._stats_cache[match_id] = (
                self.db.query(MatchStatistics).filter(MatchStatistics.match_id == match_id).first()
            )
        return self._stats_cache[match_id]

    def events_for_match(self, match_id: int) -> List[MatchEvent]:
        if match_id not in self._events_cache:
            self._events_cache[match_id] = (
                self.db.query(MatchEvent)
                .filter(MatchEvent.match_id == match_id)
                .order_by(MatchEvent.minute.asc(), MatchEvent.id.asc())
                .all()
            )
        return self._events_cache[match_id]

    def team_history(self, team_id: int, before_time: datetime.datetime, limit: int = 40) -> List[Match]:
        candidate_matches = (
            self.db.query(Match)
            .filter(
                Match.status.in_(list(FINISHED_MATCH_STATUSES)),
                Match.home_score.isnot(None),
                Match.away_score.isnot(None),
                Match.start_time < before_time,
                or_(Match.home_team_id == team_id, Match.away_team_id == team_id),
            )
            .order_by(Match.start_time.desc())
            .limit(max(1, limit * 3))
            .all()
        )

        supported = [row for row in candidate_matches if self.is_supported_match(row)]
        return supported[:limit]

    def _aggregate_team_context(
        self,
        team_id: int,
        before_time: datetime.datetime,
        history_window: int,
    ) -> Dict[str, float]:
        history = self.team_history(team_id, before_time=before_time, limit=max(5, history_window))

        if not history:
            return {
                "matches": 0,
                "points_per_match": 1.0,
                "goals_for_avg": 1.1,
                "goals_against_avg": 1.1,
                "shots_on_avg": 4.0,
                "shots_off_avg": 4.5,
                "possession_avg": 50.0,
                "corners_avg": 4.0,
                "form_points_last5": 6.0,
                "rest_days": 7.0,
                "stats_coverage": 0.0,
            }

        rows = history[:history_window]

        points = 0.0
        goals_for: List[float] = []
        goals_against: List[float] = []
        shots_on: List[float] = []
        shots_off: List[float] = []
        possessions: List[float] = []
        corners: List[float] = []
        stats_hits = 0

        form_rows = rows[:5]
        form_points = 0.0

        for match in rows:
            is_home = match.home_team_id == team_id

            team_goals = _safe_float(match.home_score if is_home else match.away_score)
            opp_goals = _safe_float(match.away_score if is_home else match.home_score)

            goals_for.append(team_goals)
            goals_against.append(opp_goals)

            if team_goals > opp_goals:
                points += 3.0
            elif team_goals == opp_goals:
                points += 1.0

            if match in form_rows:
                if team_goals > opp_goals:
                    form_points += 3.0
                elif team_goals == opp_goals:
                    form_points += 1.0

            stats = self.stats_for_match(match.id)
            if not stats:
                continue

            stats_hits += 1
            if is_home:
                shots_on.append(_safe_float(stats.shots_on_home, default=0.0))
                shots_off.append(_safe_float(stats.shots_off_home, default=0.0))
                possessions.append(_safe_float(stats.possession_home, default=50.0))
                corners.append(_safe_float(stats.corners_home, default=4.0))
            else:
                shots_on.append(_safe_float(stats.shots_on_away, default=0.0))
                shots_off.append(_safe_float(stats.shots_off_away, default=0.0))
                possessions.append(_safe_float(stats.possession_away, default=50.0))
                corners.append(_safe_float(stats.corners_away, default=4.0))

        newest_match = rows[0]
        rest_days = max(0.0, min(14.0, (before_time - newest_match.start_time).total_seconds() / 86400.0))

        matches_count = len(rows)
        stats_coverage = float(stats_hits / matches_count) if matches_count > 0 else 0.0

        return {
            "matches": float(matches_count),
            "points_per_match": round(points / matches_count, 4),
            "goals_for_avg": round(float(np.mean(goals_for)) if goals_for else 1.1, 4),
            "goals_against_avg": round(float(np.mean(goals_against)) if goals_against else 1.1, 4),
            "shots_on_avg": round(float(np.mean(shots_on)) if shots_on else 4.0, 4),
            "shots_off_avg": round(float(np.mean(shots_off)) if shots_off else 4.5, 4),
            "possession_avg": round(float(np.mean(possessions)) if possessions else 50.0, 4),
            "corners_avg": round(float(np.mean(corners)) if corners else 4.0, 4),
            "form_points_last5": round(form_points, 4),
            "rest_days": round(rest_days, 4),
            "stats_coverage": round(stats_coverage, 4),
        }

    def build_feature_row(
        self,
        match: Match,
        team_id: int,
        history_window: int,
    ) -> Tuple[Dict[str, float], Dict[str, float]]:
        opponent_id = match.away_team_id if team_id == match.home_team_id else match.home_team_id
        is_home = 1.0 if team_id == match.home_team_id else 0.0

        team_context = self._aggregate_team_context(team_id, match.start_time, history_window)
        opponent_context = self._aggregate_team_context(opponent_id, match.start_time, history_window)

        home_league = self._league_for_team(match.home_team_id)
        away_league = self._league_for_team(match.away_team_id)

        is_ucl = 1.0 if _is_ucl_name(getattr(home_league, "name", "")) or _is_ucl_name(getattr(away_league, "name", "")) else 0.0

        features = {
            "is_home": is_home,
            "team_points_per_match": team_context["points_per_match"],
            "team_goals_for_avg": team_context["goals_for_avg"],
            "team_goals_against_avg": team_context["goals_against_avg"],
            "team_shots_on_avg": team_context["shots_on_avg"],
            "team_shots_off_avg": team_context["shots_off_avg"],
            "team_possession_avg": team_context["possession_avg"],
            "team_corners_avg": team_context["corners_avg"],
            "team_form_points_last5": team_context["form_points_last5"],
            "team_rest_days": team_context["rest_days"],
            "opp_points_per_match": opponent_context["points_per_match"],
            "opp_goals_for_avg": opponent_context["goals_for_avg"],
            "opp_goals_against_avg": opponent_context["goals_against_avg"],
            "opp_shots_on_avg": opponent_context["shots_on_avg"],
            "opp_shots_off_avg": opponent_context["shots_off_avg"],
            "opp_possession_avg": opponent_context["possession_avg"],
            "opp_corners_avg": opponent_context["corners_avg"],
            "opp_form_points_last5": opponent_context["form_points_last5"],
            "opp_rest_days": opponent_context["rest_days"],
            "is_ucl_match": is_ucl,
            "team_stats_coverage": team_context["stats_coverage"],
            "opp_stats_coverage": opponent_context["stats_coverage"],
        }

        diagnostics = {
            "team_history_matches": team_context["matches"],
            "opponent_history_matches": opponent_context["matches"],
            "team_stats_coverage": team_context["stats_coverage"],
            "opponent_stats_coverage": opponent_context["stats_coverage"],
        }

        return features, diagnostics

    def build_proxy_training_frame(self, config: XGTrainingConfig) -> pd.DataFrame:
        matches = self.supported_finished_matches()
        rows: List[Dict[str, Any]] = []

        for match in matches:
            home_features, home_diag = self.build_feature_row(match, match.home_team_id, config.history_window)
            away_features, away_diag = self.build_feature_row(match, match.away_team_id, config.history_window)

            if min(home_diag["team_history_matches"], home_diag["opponent_history_matches"]) < 3:
                continue
            if min(away_diag["team_history_matches"], away_diag["opponent_history_matches"]) < 3:
                continue

            rows.append(
                {
                    "match_id": match.id,
                    "team_id": match.home_team_id,
                    "sample_time": match.start_time,
                    "target_goals": _safe_float(match.home_score),
                    "target_scored": 1.0 if _safe_float(match.home_score) > 0 else 0.0,
                    "actual_goals": _safe_float(match.home_score),
                    **home_features,
                }
            )

            rows.append(
                {
                    "match_id": match.id,
                    "team_id": match.away_team_id,
                    "sample_time": match.start_time,
                    "target_goals": _safe_float(match.away_score),
                    "target_scored": 1.0 if _safe_float(match.away_score) > 0 else 0.0,
                    "actual_goals": _safe_float(match.away_score),
                    **away_features,
                }
            )

        if not rows:
            return pd.DataFrame(columns=["match_id", "team_id", "sample_time", "target_goals", "target_scored", "actual_goals", *PROXY_FEATURE_COLUMNS])

        frame = pd.DataFrame(rows)
        return frame

    def infer_live_minute(self, match: Match, minute_override: Optional[int] = None) -> int:
        if minute_override is not None:
            return int(_clamp(float(minute_override), 0.0, 130.0))

        status = normalize_text(match.status)
        if status in {"ns", "tbd"}:
            return 0
        if status == "ht":
            return 45
        if status in {"ft", "aet", "pen"}:
            return 90

        events = self.events_for_match(match.id)
        if events:
            return int(_clamp(float(max(_safe_int(event.minute, default=1) for event in events)), 1.0, 130.0))

        if match.status in LIVE_MATCH_STATUSES:
            return 1

        return 0

    def event_signals_until(self, match: Match, minute: int) -> Dict[str, float]:
        events = self.events_for_match(match.id)
        minute = max(0, minute)

        home_bonus = 0.0
        away_bonus = 0.0

        home_goals = 0
        away_goals = 0
        red_cards_home = 0
        red_cards_away = 0

        for event in events:
            event_minute = _safe_int(event.minute, default=0)
            if event_minute > minute:
                break

            team_id = event.team_id
            event_type = event.event_type or ""
            detail = event.detail or ""

            if is_goal_event(event_type):
                if team_id == match.home_team_id:
                    home_bonus += 0.33
                    home_goals += 1
                elif team_id == match.away_team_id:
                    away_bonus += 0.33
                    away_goals += 1
                continue

            normalized_type = normalize_text(event_type)
            if "assist" in normalized_type:
                if team_id == match.home_team_id:
                    home_bonus += 0.06
                elif team_id == match.away_team_id:
                    away_bonus += 0.06
                continue

            if is_card_event(event_type):
                if is_red_card_detail(detail):
                    if team_id == match.home_team_id:
                        away_bonus += 0.08
                        red_cards_home += 1
                    elif team_id == match.away_team_id:
                        home_bonus += 0.08
                        red_cards_away += 1
                else:
                    if team_id == match.home_team_id:
                        away_bonus += 0.025
                    elif team_id == match.away_team_id:
                        home_bonus += 0.025

        return {
            "home_bonus": round(home_bonus, 4),
            "away_bonus": round(away_bonus, 4),
            "home_goal_events": float(home_goals),
            "away_goal_events": float(away_goals),
            "home_red_cards": float(red_cards_home),
            "away_red_cards": float(red_cards_away),
        }

    def stats_signals_until(self, match: Match, minute: int) -> Dict[str, float]:
        stats = self.stats_for_match(match.id)
        if not stats:
            return {
                "home_signal": 0.0,
                "away_signal": 0.0,
                "stats_available": 0.0,
            }

        scale = _clamp(minute / 90.0 if minute > 0 else 0.0, 0.0, 1.0)

        home_signal = (
            0.14 * _safe_float(stats.shots_on_home)
            + 0.055 * _safe_float(stats.shots_off_home)
            + 0.03 * _safe_float(stats.corners_home)
            + 0.004 * max(_safe_float(stats.possession_home) - 50.0, 0.0)
        )

        away_signal = (
            0.14 * _safe_float(stats.shots_on_away)
            + 0.055 * _safe_float(stats.shots_off_away)
            + 0.03 * _safe_float(stats.corners_away)
            + 0.004 * max(_safe_float(stats.possession_away) - 50.0, 0.0)
        )

        return {
            "home_signal": round(home_signal * scale, 4),
            "away_signal": round(away_signal * scale, 4),
            "stats_available": 1.0,
        }


def _split_training_frame_chronologically(
    frame: pd.DataFrame,
    test_ratio: float,
) -> Tuple[pd.DataFrame, pd.DataFrame]:
    if frame.empty:
        return frame.copy(), frame.copy()

    unique_matches = (
        frame[["match_id", "sample_time"]]
        .drop_duplicates()
        .sort_values(["sample_time", "match_id"], ascending=[True, True])
        .reset_index(drop=True)
    )

    if len(unique_matches) < 3:
        return frame.copy(), frame.iloc[0:0].copy()

    test_count = max(1, int(round(len(unique_matches) * test_ratio)))
    if test_count >= len(unique_matches):
        test_count = 1

    train_match_ids = set(unique_matches.iloc[:-test_count]["match_id"].tolist())
    test_match_ids = set(unique_matches.iloc[-test_count:]["match_id"].tolist())

    train_frame = frame[frame["match_id"].isin(train_match_ids)].copy()
    test_frame = frame[frame["match_id"].isin(test_match_ids)].copy()
    return train_frame, test_frame


def _load_true_shot_frame(db: Session, granularity: XGGranularity) -> pd.DataFrame:
    table_name = granularity.shot_table
    if not table_name:
        return pd.DataFrame()

    engine = getattr(db, "bind", None)
    if engine is None:
        return pd.DataFrame()

    inspector = inspect(engine)
    columns = {column["name"] for column in inspector.get_columns(table_name)}

    selected_columns: List[str] = [
        "match_id",
        "team_id",
        "minute",
        "x",
        "y",
        "is_goal",
    ]

    for optional_name in OPTIONAL_TRUE_XG_COLUMNS:
        if optional_name in columns:
            selected_columns.append(optional_name)

    sql = f"SELECT {', '.join(selected_columns)} FROM {table_name}"
    rows = db.execute(text(sql)).mappings().all()

    if not rows:
        return pd.DataFrame()

    frame = pd.DataFrame(rows)

    frame["x"] = pd.to_numeric(frame["x"], errors="coerce")
    frame["y"] = pd.to_numeric(frame["y"], errors="coerce")
    frame["minute"] = pd.to_numeric(frame["minute"], errors="coerce").fillna(0.0)

    frame = frame.dropna(subset=["x", "y"]).copy()
    if frame.empty:
        return frame

    frame["x"] = frame["x"].clip(lower=0.0, upper=100.0)
    frame["y"] = frame["y"].clip(lower=0.0, upper=100.0)

    frame["is_goal"] = frame["is_goal"].apply(
        lambda value: 1 if str(value).strip().lower() in {"1", "true", "t", "yes", "y"} else 0
    )

    if "shot_type" in frame.columns:
        frame["shot_type"] = frame["shot_type"].fillna("").astype(str)
    else:
        frame["shot_type"] = ""

    if "body_part" in frame.columns:
        frame["body_part"] = frame["body_part"].fillna("").astype(str)
    else:
        frame["body_part"] = ""

    if "assist_type" in frame.columns:
        frame["assist_type"] = frame["assist_type"].fillna("").astype(str)
    else:
        frame["assist_type"] = ""

    if "under_pressure" in frame.columns:
        frame["under_pressure"] = frame["under_pressure"].fillna(0)
    else:
        frame["under_pressure"] = 0

    dx = 100.0 - frame["x"].to_numpy(dtype=np.float64)
    dy = np.abs(50.0 - frame["y"].to_numpy(dtype=np.float64)
                )

    frame["shot_distance"] = np.sqrt((dx ** 2) + (dy ** 2))
    frame["shot_angle"] = np.arctan2(np.maximum(1.0, 100.0 - frame["x"].to_numpy(dtype=np.float64)), dy + 1.0)

    body_text = frame["body_part"].str.lower()
    shot_text = frame["shot_type"].str.lower()
    assist_text = frame["assist_type"].str.lower()

    frame["is_header"] = body_text.str.contains("head").astype(float)
    frame["is_set_piece"] = (
        shot_text.str.contains("pen")
        | shot_text.str.contains("free")
        | shot_text.str.contains("set")
    ).astype(float)
    frame["assist_cross"] = (
        assist_text.str.contains("cross")
        | assist_text.str.contains("set")
    ).astype(float)

    frame["under_pressure_flag"] = frame["under_pressure"].apply(
        lambda value: 1.0 if str(value).strip().lower() in {"1", "true", "t", "yes", "y"} else 0.0
    )

    return frame


def _train_true_shot_model(
    shot_frame: pd.DataFrame,
    seed: int,
) -> Tuple[Pipeline, Dict[str, Dict[str, float]], pd.DataFrame]:
    if shot_frame.empty or len(shot_frame) < 300:
        raise RuntimeError("Insufficient shot-level rows for true xG shot model training.")

    X = shot_frame[TRUE_SHOT_FEATURE_COLUMNS].to_numpy(dtype=np.float64)
    y = shot_frame["is_goal"].to_numpy(dtype=np.int64)

    if len(np.unique(y)) < 2:
        raise RuntimeError("Shot-level target has a single class; cannot train true xG shot model.")

    X_train, X_test, y_train, y_test, idx_train, idx_test = train_test_split(
        X,
        y,
        shot_frame.index.to_numpy(),
        test_size=0.2,
        random_state=seed,
        stratify=y,
    )

    model = Pipeline(
        steps=[
            ("scaler", StandardScaler()),
            (
                "classifier",
                LogisticRegression(
                    max_iter=2000,
                    class_weight="balanced",
                    solver="lbfgs",
                    random_state=seed,
                ),
            ),
        ]
    )

    model.fit(X_train, y_train)

    train_probs = model.predict_proba(X_train)[:, 1]
    test_probs = model.predict_proba(X_test)[:, 1]

    shot_eval = {
        "train": {
            "samples": int(len(y_train)),
            "log_loss": float(
                np.mean(-((y_train * np.log(np.clip(train_probs, 1e-12, 1.0))) + ((1 - y_train) * np.log(np.clip(1 - train_probs, 1e-12, 1.0)))))
            ),
            "brier": float(np.mean((train_probs - y_train) ** 2)),
            "ece_10_bin": float(_expected_calibration_error(train_probs, y_train.astype(np.float64), bins=10)),
        },
        "test": {
            "samples": int(len(y_test)),
            "log_loss": float(
                np.mean(-((y_test * np.log(np.clip(test_probs, 1e-12, 1.0))) + ((1 - y_test) * np.log(np.clip(1 - test_probs, 1e-12, 1.0)))))
            ),
            "brier": float(np.mean((test_probs - y_test) ** 2)),
            "ece_10_bin": float(_expected_calibration_error(test_probs, y_test.astype(np.float64), bins=10)),
        },
    }

    full_probs = model.predict_proba(X)[:, 1]
    scored_frame = shot_frame.copy()
    scored_frame["shot_xg"] = full_probs
    scored_frame["split"] = "train"
    scored_frame.loc[idx_test, "split"] = "test"

    return model, shot_eval, scored_frame


def _build_true_target_map(scored_shots: pd.DataFrame) -> Dict[Tuple[int, int], float]:
    grouped = (
        scored_shots.groupby(["match_id", "team_id"], as_index=False)["shot_xg"].sum().rename(columns={"shot_xg": "target_xg"})
    )

    target_map: Dict[Tuple[int, int], float] = {}
    for row in grouped.itertuples(index=False):
        target_map[(int(row.match_id), int(row.team_id))] = float(row.target_xg)

    return target_map


def _build_training_frame_from_target_map(
    builder: XGFeatureBuilder,
    config: XGTrainingConfig,
    target_map: Dict[Tuple[int, int], float],
) -> pd.DataFrame:
    rows: List[Dict[str, Any]] = []
    matches = builder.supported_finished_matches()

    for match in matches:
        for team_id, actual_goals in (
            (match.home_team_id, _safe_float(match.home_score)),
            (match.away_team_id, _safe_float(match.away_score)),
        ):
            key = (match.id, team_id)
            if key not in target_map:
                continue

            features, diagnostics = builder.build_feature_row(match, team_id, history_window=config.history_window)
            if min(diagnostics["team_history_matches"], diagnostics["opponent_history_matches"]) < 3:
                continue

            rows.append(
                {
                    "match_id": match.id,
                    "team_id": team_id,
                    "sample_time": match.start_time,
                    "target_xg": float(target_map[key]),
                    "target_scored": 1.0 if actual_goals > 0 else 0.0,
                    "actual_goals": actual_goals,
                    **features,
                }
            )

    if not rows:
        return pd.DataFrame(columns=["match_id", "team_id", "sample_time", "target_xg", "target_scored", "actual_goals", *PROXY_FEATURE_COLUMNS])

    return pd.DataFrame(rows)


def _fit_poisson_model(
    frame: pd.DataFrame,
    feature_columns: List[str],
    target_column: str,
    alpha: float,
) -> Pipeline:
    model = Pipeline(
        steps=[
            ("scaler", StandardScaler()),
            (
                "regressor",
                PoissonRegressor(
                    alpha=max(1e-6, alpha),
                    max_iter=2000,
                ),
            ),
        ]
    )

    X = frame[feature_columns].to_numpy(dtype=np.float64)
    y = frame[target_column].to_numpy(dtype=np.float64)

    model.fit(X, y)
    return model


def _evaluate_xg_regression(
    y_true: np.ndarray,
    y_pred: np.ndarray,
    actual_goals: Optional[np.ndarray],
) -> Tuple[Dict[str, float], List[Dict[str, Any]]]:
    if y_true.size == 0:
        return {
            "rows": 0,
            "mae": 0.0,
            "rmse": 0.0,
            "r2": 0.0,
            "calibration_mae_10_bin": 0.0,
            "prob_score_ge1_ece_10_bin": 0.0,
            "mean_prediction": 0.0,
            "mean_target": 0.0,
        }, []

    y_pred_clipped = np.clip(y_pred.astype(np.float64), 0.0, 8.0)
    y_true_float = y_true.astype(np.float64)

    bins, calibration_mae = _regression_calibration_bins(y_pred_clipped, y_true_float, bins=10)

    if actual_goals is None:
        binary_labels = (y_true_float > 0).astype(np.float64)
    else:
        binary_labels = (actual_goals.astype(np.float64) > 0).astype(np.float64)

    prob_score_ge1 = 1.0 - np.exp(-y_pred_clipped)
    prob_score_ge1_ece = _expected_calibration_error(prob_score_ge1, binary_labels, bins=10)

    metrics = {
        "rows": int(len(y_true_float)),
        "mae": float(mean_absolute_error(y_true_float, y_pred_clipped)),
        "rmse": float(math.sqrt(mean_squared_error(y_true_float, y_pred_clipped))),
        "r2": float(r2_score(y_true_float, y_pred_clipped)) if len(y_true_float) > 1 else 0.0,
        "calibration_mae_10_bin": float(calibration_mae),
        "prob_score_ge1_ece_10_bin": float(prob_score_ge1_ece),
        "mean_prediction": float(np.mean(y_pred_clipped)),
        "mean_target": float(np.mean(y_true_float)),
    }

    return metrics, bins


def train_xg_artifact(
    db: Session,
    config: Optional[XGTrainingConfig] = None,
) -> Dict[str, Any]:
    cfg = config or XGTrainingConfig()

    random.seed(cfg.seed)
    np.random.seed(cfg.seed)

    granularity = detect_xg_granularity(db, min_true_rows=cfg.shot_min_rows)
    builder = XGFeatureBuilder(db)

    artifact: Dict[str, Any] = {
        "version": "xg_model_v1",
        "scope": XG_SCOPE,
        "trained_at_utc": _utc_now_iso(),
        "mode": granularity.mode,
        "granularity": granularity.to_dict(),
        "config": cfg.to_dict(),
        "feature_columns": list(PROXY_FEATURE_COLUMNS),
        "feature_docs": dict(PROXY_FEATURE_DOCS),
        "target_column": "target_goals",
        "model": None,
        "metrics": {},
        "calibration_bins": {},
        "training_data": {},
        "shot_model": None,
        "shot_feature_columns": [],
        "shot_metrics": {},
        "notes": [],
    }

    training_frame: pd.DataFrame

    if granularity.mode == "true_xg":
        shot_frame = _load_true_shot_frame(db, granularity)
        if shot_frame.empty or len(shot_frame) < cfg.shot_min_rows:
            artifact["notes"].append(
                "Shot-level schema detected but rows are insufficient after preprocessing; fallback to xG proxy mode."
            )
            artifact["mode"] = "xg_proxy"
            artifact["granularity"]["reason"] = (
                "Shot-level rows became insufficient after preprocessing filters; using explicit xG proxy."
            )
            training_frame = builder.build_proxy_training_frame(cfg)
            artifact["target_column"] = "target_goals"
        else:
            shot_model, shot_metrics, scored_shots = _train_true_shot_model(shot_frame, seed=cfg.seed)
            target_map = _build_true_target_map(scored_shots)
            training_frame = _build_training_frame_from_target_map(builder, cfg, target_map)

            if training_frame.empty or len(training_frame) < cfg.min_training_rows:
                artifact["notes"].append(
                    "True xG shot model was trained, but pre-match team target rows were insufficient; fallback to xG proxy mode."
                )
                artifact["mode"] = "xg_proxy"
                artifact["granularity"]["reason"] = (
                    "Shot model exists but team-level supervised rows are insufficient for stable pre-match forecasts; using proxy."
                )
                training_frame = builder.build_proxy_training_frame(cfg)
                artifact["target_column"] = "target_goals"
            else:
                artifact["target_column"] = "target_xg"
                artifact["shot_model"] = shot_model
                artifact["shot_feature_columns"] = list(TRUE_SHOT_FEATURE_COLUMNS)
                artifact["shot_metrics"] = shot_metrics
                artifact["feature_docs"].update(TRUE_SHOT_FEATURE_DOCS)
    else:
        training_frame = builder.build_proxy_training_frame(cfg)

    if training_frame.empty or len(training_frame) < cfg.min_training_rows:
        raise RuntimeError(
            "Insufficient training rows for xG module. "
            f"rows={len(training_frame)} required_min={cfg.min_training_rows}"
        )

    target_column = artifact["target_column"]

    train_frame, test_frame = _split_training_frame_chronologically(training_frame, test_ratio=cfg.test_ratio)
    if train_frame.empty:
        raise RuntimeError("Training frame is empty after chronological split.")

    model = _fit_poisson_model(
        frame=train_frame,
        feature_columns=PROXY_FEATURE_COLUMNS,
        target_column=target_column,
        alpha=cfg.poisson_alpha,
    )

    train_pred = model.predict(train_frame[PROXY_FEATURE_COLUMNS].to_numpy(dtype=np.float64))
    test_pred = (
        model.predict(test_frame[PROXY_FEATURE_COLUMNS].to_numpy(dtype=np.float64))
        if not test_frame.empty
        else np.array([], dtype=np.float64)
    )

    train_metrics, train_bins = _evaluate_xg_regression(
        y_true=train_frame[target_column].to_numpy(dtype=np.float64),
        y_pred=train_pred,
        actual_goals=train_frame["actual_goals"].to_numpy(dtype=np.float64),
    )

    test_metrics, test_bins = _evaluate_xg_regression(
        y_true=test_frame[target_column].to_numpy(dtype=np.float64),
        y_pred=test_pred,
        actual_goals=test_frame["actual_goals"].to_numpy(dtype=np.float64) if not test_frame.empty else None,
    )

    artifact["model"] = model
    artifact["metrics"] = {
        "train": train_metrics,
        "test": test_metrics,
    }
    artifact["calibration_bins"] = {
        "train": train_bins,
        "test": test_bins,
    }
    artifact["training_data"] = {
        "rows": int(len(training_frame)),
        "unique_matches": int(training_frame["match_id"].nunique()),
        "unique_teams": int(training_frame["team_id"].nunique()),
        "train_rows": int(len(train_frame)),
        "test_rows": int(len(test_frame)),
        "target_column": target_column,
    }

    if artifact["mode"] == "xg_proxy":
        artifact["notes"].append(
            "xG proxy uses aggregate match statistics and team history. It is not shot-by-shot true xG."
        )

    return artifact


def save_xg_artifact(artifact: Dict[str, Any], artifact_path: Path = DEFAULT_XG_ARTIFACT_PATH) -> Path:
    artifact_path.parent.mkdir(parents=True, exist_ok=True)
    with artifact_path.open("wb") as file_obj:
        pickle.dump(artifact, file_obj)
    return artifact_path


def load_xg_artifact(artifact_path: Path = DEFAULT_XG_ARTIFACT_PATH) -> Optional[Dict[str, Any]]:
    if not artifact_path.exists():
        return None

    with artifact_path.open("rb") as file_obj:
        return pickle.load(file_obj)


def build_metrics_view(artifact: Dict[str, Any]) -> Dict[str, Any]:
    return {
        "version": artifact.get("version"),
        "scope": artifact.get("scope"),
        "trained_at_utc": artifact.get("trained_at_utc"),
        "mode": artifact.get("mode"),
        "granularity": artifact.get("granularity", {}),
        "target_column": artifact.get("target_column"),
        "training_data": artifact.get("training_data", {}),
        "metrics": artifact.get("metrics", {}),
        "calibration_bins": artifact.get("calibration_bins", {}),
        "shot_metrics": artifact.get("shot_metrics", {}),
        "notes": artifact.get("notes", []),
    }


def write_feature_documentation(artifact: Dict[str, Any], destination: Path = DEFAULT_XG_FEATURE_DOC_PATH) -> Path:
    destination.parent.mkdir(parents=True, exist_ok=True)

    docs = artifact.get("feature_docs", {})
    mode = artifact.get("mode", "xg_proxy")
    granularity = artifact.get("granularity", {})

    lines = [
        "# xG Feature Documentation",
        "",
        f"- Scope: {artifact.get('scope', XG_SCOPE)}",
        f"- Model mode: {mode}",
        f"- Trained at (UTC): {artifact.get('trained_at_utc', 'unknown')}",
        f"- Granularity note: {granularity.get('reason', 'n/a')}",
        "",
        "## Feature Catalog",
        "",
        "| Feature | Description |",
        "|---|---|",
    ]

    for feature_name in artifact.get("feature_columns", []):
        lines.append(f"| {feature_name} | {docs.get(feature_name, 'No description provided.')} |")

    if mode == "true_xg" and artifact.get("shot_feature_columns"):
        lines.extend([
            "",
            "## Shot-Level True xG Inputs",
            "",
            "| Feature | Description |",
            "|---|---|",
        ])
        for feature_name in artifact.get("shot_feature_columns", []):
            lines.append(f"| {feature_name} | {docs.get(feature_name, 'No description provided.')} |")

    lines.extend(
        [
            "",
            "## Notes",
            "",
            "- xG proxy mode is explicitly labeled and should not be interpreted as event-level true xG.",
            "- Confidence and calibration outputs are included in training metrics JSON.",
        ]
    )

    destination.write_text("\n".join(lines), encoding="utf-8")
    return destination


def _dedupe_notes(notes: List[str]) -> List[str]:
    deduped: List[str] = []
    for note in notes:
        if note and note not in deduped:
            deduped.append(note)
    return deduped


def _confidence_from_metrics(
    artifact: Optional[Dict[str, Any]],
    diagnostics: Dict[str, float],
) -> Tuple[float, str]:
    if not artifact:
        coverage = (diagnostics.get("team_stats_coverage", 0.0) + diagnostics.get("opponent_stats_coverage", 0.0)) / 2.0
        score = _clamp(0.25 + (0.35 * coverage), 0.15, 0.65)
    else:
        test_metrics = artifact.get("metrics", {}).get("test", {})
        mae = _safe_float(test_metrics.get("mae"), default=1.2)

        base = _clamp(1.0 - (mae / 2.5), 0.1, 0.95)
        coverage = (diagnostics.get("team_stats_coverage", 0.0) + diagnostics.get("opponent_stats_coverage", 0.0)) / 2.0
        history = min(diagnostics.get("team_history_matches", 0.0), diagnostics.get("opponent_history_matches", 0.0))
        history_factor = _clamp(history / 10.0, 0.2, 1.0)

        score = _clamp((0.55 * base) + (0.30 * coverage) + (0.15 * history_factor), 0.1, 0.95)

    if score >= 0.72:
        return score, "high"
    if score >= 0.5:
        return score, "medium"
    return score, "low"


def _heuristic_xg_from_features(features: Dict[str, float]) -> float:
    estimate = (
        0.48 * features.get("team_goals_for_avg", 1.1)
        + 0.32 * features.get("opp_goals_against_avg", 1.1)
        + 0.11 * features.get("team_shots_on_avg", 4.0)
        + 0.04 * features.get("team_shots_off_avg", 4.5)
        + 0.02 * features.get("team_corners_avg", 4.0)
        + (0.12 if features.get("is_home", 0.0) >= 0.5 else 0.0)
    )
    return float(_clamp(estimate, 0.05, 5.5))


def _live_cumulative_xg(
    pre_match_xg: float,
    minute: int,
    stat_signal: float,
    event_bonus: float,
) -> float:
    if minute <= 0:
        return 0.0

    time_ratio = _clamp(minute / 90.0, 0.0, 1.25)
    baseline = pre_match_xg * min(time_ratio, 1.0)
    value = (0.68 * baseline) + (0.32 * stat_signal) + event_bonus
    return float(_clamp(value, 0.0, 8.0))


class XGInferenceService:
    def __init__(self, artifact_path: Path = DEFAULT_XG_ARTIFACT_PATH):
        self.artifact_path = artifact_path
        self._artifact: Optional[Dict[str, Any]] = None
        self._artifact_mtime: Optional[float] = None

    def _refresh_artifact(self) -> Optional[Dict[str, Any]]:
        if not self.artifact_path.exists():
            self._artifact = None
            self._artifact_mtime = None
            return None

        mtime = self.artifact_path.stat().st_mtime
        if self._artifact is None or self._artifact_mtime != mtime:
            self._artifact = load_xg_artifact(self.artifact_path)
            self._artifact_mtime = mtime

        return self._artifact

    def _predict_team_xg(
        self,
        artifact: Optional[Dict[str, Any]],
        feature_row: Dict[str, float],
    ) -> Tuple[float, str]:
        if artifact and artifact.get("model") is not None:
            model = artifact["model"]
            columns = artifact.get("feature_columns", PROXY_FEATURE_COLUMNS)
            vector = np.array([[feature_row.get(column, 0.0) for column in columns]], dtype=np.float64)
            prediction = float(model.predict(vector)[0])
            return _clamp(prediction, 0.0, 8.0), "trained_model"

        return _heuristic_xg_from_features(feature_row), "heuristic_fallback"

    def predict_pre_match(self, db: Session, match: Match) -> Dict[str, Any]:
        artifact = self._refresh_artifact()
        builder = XGFeatureBuilder(db)

        history_window = 12
        if artifact:
            history_window = _safe_int(artifact.get("config", {}).get("history_window"), default=12)
            history_window = max(3, min(30, history_window))

        home_team = builder._team(match.home_team_id)
        away_team = builder._team(match.away_team_id)

        home_features, home_diag = builder.build_feature_row(match, match.home_team_id, history_window=history_window)
        away_features, away_diag = builder.build_feature_row(match, match.away_team_id, history_window=history_window)

        home_xg, home_source = self._predict_team_xg(artifact, home_features)
        away_xg, away_source = self._predict_team_xg(artifact, away_features)

        diagnostics = {
            "team_history_matches": min(home_diag.get("team_history_matches", 0.0), away_diag.get("team_history_matches", 0.0)),
            "opponent_history_matches": min(home_diag.get("opponent_history_matches", 0.0), away_diag.get("opponent_history_matches", 0.0)),
            "team_stats_coverage": (home_diag.get("team_stats_coverage", 0.0) + away_diag.get("team_stats_coverage", 0.0)) / 2.0,
            "opponent_stats_coverage": (home_diag.get("opponent_stats_coverage", 0.0) + away_diag.get("opponent_stats_coverage", 0.0)) / 2.0,
        }

        confidence_score, confidence_label = _confidence_from_metrics(artifact, diagnostics)

        mode = "xg_proxy"
        granularity_reason = "No trained artifact was found; using fallback xG proxy estimate."
        training_rows = 0
        calibration_summary = {}

        if artifact:
            mode = str(artifact.get("mode", "xg_proxy"))
            granularity_reason = str(artifact.get("granularity", {}).get("reason", ""))
            training_rows = int(artifact.get("training_data", {}).get("rows", 0))
            test_metrics = artifact.get("metrics", {}).get("test", {})
            calibration_summary = {
                "test_calibration_mae_10_bin": _safe_float(test_metrics.get("calibration_mae_10_bin")),
                "test_prob_score_ge1_ece_10_bin": _safe_float(test_metrics.get("prob_score_ge1_ece_10_bin")),
            }

        disclaimers = [
            granularity_reason,
            "xG values are forecasts and should be interpreted with uncertainty.",
        ]

        if mode != "true_xg":
            disclaimers.append(
                "This is an explicitly labeled xG proxy because shot-level coordinates/context are unavailable in the current dataset."
            )

        if home_source != "trained_model" or away_source != "trained_model":
            disclaimers.append("Trained xG artifact is missing; heuristic fallback is active.")

        if min(home_diag.get("team_history_matches", 0.0), away_diag.get("team_history_matches", 0.0)) < 5:
            disclaimers.append("Recent historical sample is limited for one or both teams, reducing reliability.")

        payload = {
            "match_id": match.id,
            "scope": XG_SCOPE,
            "generated_at_utc": _utc_now_iso(),
            "model": {
                "mode": mode,
                "is_proxy": mode != "true_xg",
                "model_version": artifact.get("version") if artifact else "xg_proxy_heuristic",
                "trained_at_utc": artifact.get("trained_at_utc") if artifact else None,
                "confidence_score": round(float(confidence_score), 4),
                "confidence_label": confidence_label,
                "granularity_reason": granularity_reason,
                "training_sample_size": training_rows,
                "calibration_summary": calibration_summary,
            },
            "home": {
                "team_id": match.home_team_id,
                "team_name": home_team.name if home_team else f"Team {match.home_team_id}",
                "xg": round(float(home_xg), 3),
            },
            "away": {
                "team_id": match.away_team_id,
                "team_name": away_team.name if away_team else f"Team {match.away_team_id}",
                "xg": round(float(away_xg), 3),
            },
            "expected_total_xg": round(float(home_xg + away_xg), 3),
            "feature_coverage": {
                "home_team_history_matches": int(home_diag.get("team_history_matches", 0.0)),
                "away_team_history_matches": int(away_diag.get("team_history_matches", 0.0)),
                "home_stats_coverage": round(float(home_diag.get("team_stats_coverage", 0.0)), 4),
                "away_stats_coverage": round(float(away_diag.get("team_stats_coverage", 0.0)), 4),
            },
            "disclaimers": _dedupe_notes(disclaimers),
        }

        return payload

    def predict_live(
        self,
        db: Session,
        match: Match,
        minute_override: Optional[int] = None,
    ) -> Dict[str, Any]:
        pre_match = self.predict_pre_match(db, match)
        builder = XGFeatureBuilder(db)

        minute_context = builder.infer_live_minute(match, minute_override=minute_override)

        if minute_context <= 0:
            timeline_minutes = [0]
        else:
            base_ticks = [0, 15, 30, 45, 60, 75, 90]
            if minute_context < 90:
                timeline_minutes = sorted({tick for tick in base_ticks if tick <= minute_context} | {minute_context})
            else:
                timeline_minutes = sorted(set(base_ticks + [minute_context]))

        home_pre_xg = _safe_float(pre_match["home"]["xg"])
        away_pre_xg = _safe_float(pre_match["away"]["xg"])

        timeline = []
        current_event_signals = builder.event_signals_until(match, minute_context)
        current_stats_signals = builder.stats_signals_until(match, minute_context)

        for point_minute in timeline_minutes:
            event_signals = builder.event_signals_until(match, point_minute)
            stats_signals = builder.stats_signals_until(match, point_minute)

            home_live_xg = _live_cumulative_xg(
                pre_match_xg=home_pre_xg,
                minute=point_minute,
                stat_signal=stats_signals["home_signal"],
                event_bonus=event_signals["home_bonus"],
            )
            away_live_xg = _live_cumulative_xg(
                pre_match_xg=away_pre_xg,
                minute=point_minute,
                stat_signal=stats_signals["away_signal"],
                event_bonus=event_signals["away_bonus"],
            )

            timeline.append(
                {
                    "minute": int(point_minute),
                    "home_xg": round(float(home_live_xg), 3),
                    "away_xg": round(float(away_live_xg), 3),
                }
            )

        home_current_xg = timeline[-1]["home_xg"] if timeline else 0.0
        away_current_xg = timeline[-1]["away_xg"] if timeline else 0.0

        live_disclaimers = list(pre_match.get("disclaimers", []))
        live_disclaimers.extend(
            [
                "Live xG trend is updated from available match events and aggregate stats, not from shot-by-shot tracking.",
                "Event feed delays or missing stats can temporarily distort the live trend.",
            ]
        )

        return {
            "match_id": match.id,
            "scope": pre_match.get("scope", XG_SCOPE),
            "generated_at_utc": _utc_now_iso(),
            "model": pre_match.get("model", {}),
            "minute_context": int(minute_context),
            "home_current_xg": round(float(home_current_xg), 3),
            "away_current_xg": round(float(away_current_xg), 3),
            "timeline": timeline,
            "pre_match_baseline": {
                "home_xg": round(float(home_pre_xg), 3),
                "away_xg": round(float(away_pre_xg), 3),
            },
            "live_signals": {
                "home_event_boost": round(float(current_event_signals["home_bonus"]), 4),
                "away_event_boost": round(float(current_event_signals["away_bonus"]), 4),
                "home_stats_signal": round(float(current_stats_signals["home_signal"]), 4),
                "away_stats_signal": round(float(current_stats_signals["away_signal"]), 4),
                "stats_available": bool(current_stats_signals.get("stats_available", 0.0) > 0),
                "home_goal_events": int(current_event_signals.get("home_goal_events", 0.0)),
                "away_goal_events": int(current_event_signals.get("away_goal_events", 0.0)),
            },
            "disclaimers": _dedupe_notes(live_disclaimers),
        }


xg_inference_service = XGInferenceService()
