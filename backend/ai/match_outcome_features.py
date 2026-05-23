"""Feature engineering for the 1X2 match-outcome model.

Two callable surfaces:

- `build_training_frame(db)` returns a `pandas.DataFrame` covering every
  finished match in the supported scope, with the chronological order
  preserved. Each row is a fully self-contained training example: only
  data available *before* `start_time` is included, so a temporal split
  on `start_time` is leakage-free.

- `build_inference_features(db, match)` returns a single feature vector
  for an upcoming or live match using the same logic.

The feature set was intentionally expanded after the v1 baseline
(13 features) plateaued at 47% accuracy because the network never
predicted draws. The additional signals target three known weaknesses:

1. Strength differential (`elo_ratio`, `goal_diff_avg`, `form_diff_*`)
   gives the network a clearer notion of "balanced fixture", which is
   the regime where draws actually happen.
2. League context (`league_*` dummies) lets the model learn that, e.g.,
   Serie A has a markedly higher draw rate than the Premier League.
3. Head-to-head history (`h2h_*`) captures team-pair dynamics that
   season-aggregate stats miss entirely.
"""

from __future__ import annotations

import datetime
from typing import Any, Dict, List, Optional, Tuple

import numpy as np
import pandas as pd
from sqlalchemy import or_
from sqlalchemy.orm import Session

try:
    from backend.ai.elo import DEFAULT_RATING
    from backend.models import League, Match, Team, TeamEloSnapshot
except ImportError:
    from ai.elo import DEFAULT_RATING  # type: ignore[no-redef]
    from models import League, Match, Team, TeamEloSnapshot  # type: ignore[no-redef]


FINISHED_STATUSES = {"FT", "AET", "PEN"}

# League IDs we'll one-hot encode. Anything else falls back to a single
# `league_other` indicator.
KNOWN_LEAGUE_IDS = {
    2021: "premier_league",
    2014: "la_liga",
    2002: "bundesliga",
    2019: "serie_a",
    2015: "ligue_1",
    2001: "ucl",
}

FEATURE_COLUMNS: List[str] = [
    # --- Strength baselines ---
    "home_elo_pre",
    "away_elo_pre",
    "elo_diff",
    "elo_ratio",
    # --- Recent form ---
    "home_form_points_5",
    "away_form_points_5",
    "form_diff_5",
    "home_home_form_5",
    "away_away_form_5",
    "venue_form_diff",
    # --- Goals ---
    "home_goals_for_avg_10",
    "away_goals_for_avg_10",
    "home_goals_against_avg_10",
    "away_goals_against_avg_10",
    "home_goal_diff_avg_10",
    "away_goal_diff_avg_10",
    "home_btts_rate_10",
    "away_btts_rate_10",
    # --- Form against strong opponents ---
    "home_form_vs_strong_5",
    "away_form_vs_strong_5",
    # --- Rest & calendar ---
    "rest_days_diff",
    "is_weekend",
    # --- Head-to-head (last 5 meetings between these teams) ---
    "h2h_home_win_rate",
    "h2h_draw_rate",
    "h2h_avg_goals",
    # --- League dummies ---
    "league_premier_league",
    "league_la_liga",
    "league_bundesliga",
    "league_serie_a",
    "league_ligue_1",
    "league_ucl",
    "league_other",
]


def _outcome_label(home_score: int, away_score: int) -> int:
    if home_score > away_score:
        return 0  # Home win
    if home_score < away_score:
        return 2  # Away win
    return 1  # Draw


def _points_from_result(team_goals: int, opponent_goals: int) -> int:
    if team_goals > opponent_goals:
        return 3
    if team_goals == opponent_goals:
        return 1
    return 0


# ---------------------------------------------------------------------------
# Bulk training frame
# ---------------------------------------------------------------------------


def _league_dummy_columns(league_id: Optional[int]) -> Dict[str, float]:
    cols = {f"league_{name}": 0.0 for name in KNOWN_LEAGUE_IDS.values()}
    cols["league_other"] = 0.0

    if league_id in KNOWN_LEAGUE_IDS:
        cols[f"league_{KNOWN_LEAGUE_IDS[league_id]}"] = 1.0
    else:
        cols["league_other"] = 1.0

    return cols


def _resolve_league_id(match: Match, team_league_by_team_id: Dict[int, Optional[int]]) -> Optional[int]:
    if match.league_id is not None:
        return match.league_id
    return team_league_by_team_id.get(match.home_team_id) or team_league_by_team_id.get(match.away_team_id)


def build_training_frame(db: Session) -> pd.DataFrame:
    """Return one row per finished, supported match in chronological order.

    Bulk-loads matches and Elo snapshots in two queries, then computes
    rolling features in pandas. This keeps the training loop independent
    of the Supabase pool.
    """
    finished_q = (
        db.query(Match)
        .filter(Match.status.in_(FINISHED_STATUSES))
        .filter(Match.home_score.isnot(None))
        .filter(Match.away_score.isnot(None))
        .filter(Match.start_time.isnot(None))
        .order_by(Match.start_time.asc(), Match.id.asc())
    )
    matches = finished_q.all()

    if not matches:
        return pd.DataFrame()

    match_ids = [m.id for m in matches]

    snapshots = (
        db.query(TeamEloSnapshot)
        .filter(TeamEloSnapshot.match_id.in_(match_ids))
        .all()
    )
    elo_by_key: Dict[Tuple[int, int], float] = {
        (s.team_id, s.match_id): float(s.pre_match_elo) for s in snapshots
    }

    # team_id -> league_id, used for fallback when Match.league_id is null.
    team_league_pairs = db.query(Team.id, Team.league_id).all()
    team_league_by_team_id = {tid: lid for tid, lid in team_league_pairs}

    matches_df = pd.DataFrame(
        [
            {
                "match_id": m.id,
                "home_team_id": m.home_team_id,
                "away_team_id": m.away_team_id,
                "start_time": m.start_time,
                "home_score": m.home_score,
                "away_score": m.away_score,
                "league_id": _resolve_league_id(m, team_league_by_team_id),
            }
            for m in matches
        ]
    )

    # Per-team chronological log: each match contributes two rows.
    team_rows: List[Dict[str, Any]] = []
    for m in matches:
        # Pre-match Elo of the *opponent* in this fixture (lets us mark the
        # row as "vs strong" without a second pass).
        opp_pre_for_home = elo_by_key.get((m.away_team_id, m.id), DEFAULT_RATING)
        opp_pre_for_away = elo_by_key.get((m.home_team_id, m.id), DEFAULT_RATING)

        team_rows.append(
            {
                "team_id": m.home_team_id,
                "match_id": m.id,
                "start_time": m.start_time,
                "is_home": True,
                "goals_for": m.home_score,
                "goals_against": m.away_score,
                "result_points": _points_from_result(m.home_score, m.away_score),
                "opp_pre_elo": opp_pre_for_home,
            }
        )
        team_rows.append(
            {
                "team_id": m.away_team_id,
                "match_id": m.id,
                "start_time": m.start_time,
                "is_home": False,
                "goals_for": m.away_score,
                "goals_against": m.home_score,
                "result_points": _points_from_result(m.away_score, m.home_score),
                "opp_pre_elo": opp_pre_for_away,
            }
        )

    team_log = (
        pd.DataFrame(team_rows)
        .sort_values(["team_id", "start_time", "match_id"])
        .reset_index(drop=True)
    )

    # All rolling stats use shift(1) so the current match never enters its
    # own features. min_periods=1 ensures cold starts produce a value
    # rather than NaN.
    grouped = team_log.groupby("team_id", group_keys=False)

    team_log["form_points_5"] = grouped["result_points"].apply(
        lambda s: s.shift(1).rolling(5, min_periods=1).sum() / 15.0
    )
    team_log["goals_for_avg_10"] = grouped["goals_for"].apply(
        lambda s: s.shift(1).rolling(10, min_periods=1).mean()
    )
    team_log["goals_against_avg_10"] = grouped["goals_against"].apply(
        lambda s: s.shift(1).rolling(10, min_periods=1).mean()
    )
    team_log["goal_diff_avg_10"] = (team_log["goals_for_avg_10"] - team_log["goals_against_avg_10"]).astype(float)

    team_log["btts_flag"] = ((team_log["goals_for"] > 0) & (team_log["goals_against"] > 0)).astype(float)
    team_log["btts_rate_10"] = grouped["btts_flag"].apply(
        lambda s: s.shift(1).rolling(10, min_periods=1).mean()
    )

    # "Strong opponent" = pre-match Elo >= 1600 (covers the top ~30% of
    # supported clubs). `points_vs_strong` is null when the opponent isn't
    # strong, so the rolling mean naturally averages only the strong-opp
    # results.
    team_log["points_vs_strong"] = np.where(
        team_log["opp_pre_elo"] >= 1600.0,
        team_log["result_points"].astype(float) / 3.0,
        np.nan,
    )
    team_log["form_vs_strong_5"] = grouped["points_vs_strong"].apply(
        lambda s: s.shift(1).rolling(5, min_periods=1).mean()
    )

    team_log["prev_start_time"] = grouped["start_time"].shift(1)

    # Venue-specific form (home form for home rows, away form for away rows).
    home_slice = team_log[team_log["is_home"]].copy()
    home_slice["home_form_5"] = (
        home_slice.groupby("team_id", group_keys=False)["result_points"]
        .apply(lambda s: s.shift(1).rolling(5, min_periods=1).sum() / 15.0)
    )
    away_slice = team_log[~team_log["is_home"]].copy()
    away_slice["away_form_5"] = (
        away_slice.groupby("team_id", group_keys=False)["result_points"]
        .apply(lambda s: s.shift(1).rolling(5, min_periods=1).sum() / 15.0)
    )

    venue_form = pd.concat(
        [
            home_slice[["match_id", "team_id", "home_form_5"]].rename(columns={"home_form_5": "venue_form_5"}),
            away_slice[["match_id", "team_id", "away_form_5"]].rename(columns={"away_form_5": "venue_form_5"}),
        ]
    )
    team_log = team_log.merge(venue_form, on=["match_id", "team_id"], how="left")

    home_team_log = team_log[team_log["is_home"]].rename(
        columns={
            "form_points_5": "home_form_points_5",
            "goals_for_avg_10": "home_goals_for_avg_10",
            "goals_against_avg_10": "home_goals_against_avg_10",
            "goal_diff_avg_10": "home_goal_diff_avg_10",
            "btts_rate_10": "home_btts_rate_10",
            "form_vs_strong_5": "home_form_vs_strong_5",
            "venue_form_5": "home_home_form_5",
            "prev_start_time": "home_prev_start",
        }
    )[
        [
            "match_id",
            "home_form_points_5",
            "home_goals_for_avg_10",
            "home_goals_against_avg_10",
            "home_goal_diff_avg_10",
            "home_btts_rate_10",
            "home_form_vs_strong_5",
            "home_home_form_5",
            "home_prev_start",
        ]
    ]

    away_team_log = team_log[~team_log["is_home"]].rename(
        columns={
            "form_points_5": "away_form_points_5",
            "goals_for_avg_10": "away_goals_for_avg_10",
            "goals_against_avg_10": "away_goals_against_avg_10",
            "goal_diff_avg_10": "away_goal_diff_avg_10",
            "btts_rate_10": "away_btts_rate_10",
            "form_vs_strong_5": "away_form_vs_strong_5",
            "venue_form_5": "away_away_form_5",
            "prev_start_time": "away_prev_start",
        }
    )[
        [
            "match_id",
            "away_form_points_5",
            "away_goals_for_avg_10",
            "away_goals_against_avg_10",
            "away_goal_diff_avg_10",
            "away_btts_rate_10",
            "away_form_vs_strong_5",
            "away_away_form_5",
            "away_prev_start",
        ]
    ]

    df = matches_df.merge(home_team_log, on="match_id", how="left").merge(
        away_team_log, on="match_id", how="left"
    )

    df["home_elo_pre"] = df.apply(
        lambda row: elo_by_key.get((row["home_team_id"], row["match_id"]), DEFAULT_RATING),
        axis=1,
    )
    df["away_elo_pre"] = df.apply(
        lambda row: elo_by_key.get((row["away_team_id"], row["match_id"]), DEFAULT_RATING),
        axis=1,
    )
    df["elo_diff"] = df["home_elo_pre"] - df["away_elo_pre"]
    df["elo_ratio"] = df["home_elo_pre"] / df["away_elo_pre"].replace(0.0, DEFAULT_RATING)

    df["form_diff_5"] = df["home_form_points_5"] - df["away_form_points_5"]
    df["venue_form_diff"] = df["home_home_form_5"] - df["away_away_form_5"]

    df["home_rest_days"] = (df["start_time"] - df["home_prev_start"]).dt.total_seconds() / 86400.0
    df["away_rest_days"] = (df["start_time"] - df["away_prev_start"]).dt.total_seconds() / 86400.0
    df["home_rest_days"] = df["home_rest_days"].clip(lower=0.0, upper=30.0).fillna(7.0)
    df["away_rest_days"] = df["away_rest_days"].clip(lower=0.0, upper=30.0).fillna(7.0)
    df["rest_days_diff"] = df["home_rest_days"] - df["away_rest_days"]

    df["is_weekend"] = df["start_time"].dt.weekday.ge(5).astype(float)

    # Head-to-head: aggregate the last 5 meetings between the same two
    # teams, in any direction, that occurred *before* the current match.
    h2h = _build_h2h_table(matches)
    df = df.merge(h2h, on="match_id", how="left")

    # League one-hot.
    league_dummy_cols = pd.DataFrame(
        [_league_dummy_columns(int(lid) if pd.notna(lid) else None) for lid in df["league_id"]]
    )
    df = pd.concat([df.reset_index(drop=True), league_dummy_cols.reset_index(drop=True)], axis=1)

    # Defaults for cold-start rows so the network sees neutral values.
    fill_defaults = {
        "home_form_points_5": 0.5,
        "away_form_points_5": 0.5,
        "home_goals_for_avg_10": 1.2,
        "away_goals_for_avg_10": 1.2,
        "home_goals_against_avg_10": 1.2,
        "away_goals_against_avg_10": 1.2,
        "home_goal_diff_avg_10": 0.0,
        "away_goal_diff_avg_10": 0.0,
        "home_btts_rate_10": 0.5,
        "away_btts_rate_10": 0.5,
        "home_home_form_5": 0.5,
        "away_away_form_5": 0.5,
        "home_form_vs_strong_5": 0.33,
        "away_form_vs_strong_5": 0.33,
        "h2h_home_win_rate": 0.45,
        "h2h_draw_rate": 0.25,
        "h2h_avg_goals": 2.6,
    }
    for col, default in fill_defaults.items():
        df[col] = df[col].fillna(default)

    df["form_diff_5"] = df["home_form_points_5"] - df["away_form_points_5"]
    df["venue_form_diff"] = df["home_home_form_5"] - df["away_away_form_5"]

    df["label"] = df.apply(lambda row: _outcome_label(row["home_score"], row["away_score"]), axis=1)

    return df.reset_index(drop=True)


def _build_h2h_table(matches: List[Match]) -> pd.DataFrame:
    """For each match, look back at past meetings between the same two
    teams (regardless of which side hosted) and aggregate the last 5.
    """
    history: Dict[Tuple[int, int], List[Tuple[datetime.datetime, int, int, int, int]]] = {}
    rows: List[Dict[str, Any]] = []

    for m in matches:
        key = tuple(sorted([m.home_team_id, m.away_team_id]))
        past = history.get(key, [])
        # Use the last 5 recorded meetings.
        recent = past[-5:]

        home_wins = 0
        draws = 0
        total_goals = 0
        for _ts, recorded_home, _recorded_away, recorded_home_score, recorded_away_score in recent:
            total_goals += recorded_home_score + recorded_away_score
            # We want the rate for the *current* match's home team.
            if recorded_home == m.home_team_id:
                # Past meeting was hosted by today's home team.
                if recorded_home_score > recorded_away_score:
                    home_wins += 1
                elif recorded_home_score == recorded_away_score:
                    draws += 1
            else:
                # Past meeting reversed: today's home team was the visitor.
                if recorded_away_score > recorded_home_score:
                    home_wins += 1
                elif recorded_home_score == recorded_away_score:
                    draws += 1

        n = len(recent)
        if n == 0:
            home_win_rate = np.nan
            draw_rate = np.nan
            avg_goals = np.nan
        else:
            home_win_rate = home_wins / n
            draw_rate = draws / n
            avg_goals = total_goals / n

        rows.append(
            {
                "match_id": m.id,
                "h2h_home_win_rate": home_win_rate,
                "h2h_draw_rate": draw_rate,
                "h2h_avg_goals": avg_goals,
            }
        )

        # Then push *this* match into the history so future meetings see it.
        history.setdefault(key, []).append(
            (m.start_time, m.home_team_id, m.away_team_id, m.home_score, m.away_score)
        )

    return pd.DataFrame(rows)


# ---------------------------------------------------------------------------
# Single-match inference
# ---------------------------------------------------------------------------


def _team_pre_match_elo(db: Session, team_id: int, match_id: int) -> Optional[float]:
    snap = (
        db.query(TeamEloSnapshot)
        .filter(TeamEloSnapshot.team_id == team_id)
        .filter(TeamEloSnapshot.match_id == match_id)
        .first()
    )
    return float(snap.pre_match_elo) if snap else None


def _team_latest_post_elo(db: Session, team_id: int, before: datetime.datetime) -> float:
    snap = (
        db.query(TeamEloSnapshot)
        .filter(TeamEloSnapshot.team_id == team_id)
        .filter(TeamEloSnapshot.snapshot_at < before)
        .order_by(TeamEloSnapshot.snapshot_at.desc())
        .first()
    )
    return float(snap.post_match_elo) if snap else DEFAULT_RATING


def _recent_finished(
    db: Session, team_id: int, before: datetime.datetime, limit: int = 10
) -> List[Match]:
    return (
        db.query(Match)
        .filter(Match.status.in_(FINISHED_STATUSES))
        .filter(or_(Match.home_team_id == team_id, Match.away_team_id == team_id))
        .filter(Match.start_time < before)
        .filter(Match.home_score.isnot(None))
        .filter(Match.away_score.isnot(None))
        .order_by(Match.start_time.desc())
        .limit(limit)
        .all()
    )


def _recent_finished_at_venue(
    db: Session, team_id: int, before: datetime.datetime, is_home: bool, limit: int = 5
) -> List[Match]:
    if is_home:
        condition = Match.home_team_id == team_id
    else:
        condition = Match.away_team_id == team_id
    return (
        db.query(Match)
        .filter(Match.status.in_(FINISHED_STATUSES))
        .filter(condition)
        .filter(Match.start_time < before)
        .filter(Match.home_score.isnot(None))
        .filter(Match.away_score.isnot(None))
        .order_by(Match.start_time.desc())
        .limit(limit)
        .all()
    )


def _form_points(matches: List[Match], team_id: int) -> float:
    if not matches:
        return 0.5  # neutral default
    points = 0
    for m in matches:
        if m.home_team_id == team_id:
            points += _points_from_result(m.home_score, m.away_score)
        else:
            points += _points_from_result(m.away_score, m.home_score)
    return points / float(len(matches) * 3)


def _goals_avg(matches: List[Match], team_id: int, scored: bool) -> float:
    if not matches:
        return 1.2
    vals: List[int] = []
    for m in matches:
        if m.home_team_id == team_id:
            vals.append(m.home_score if scored else m.away_score)
        else:
            vals.append(m.away_score if scored else m.home_score)
    return float(np.mean(vals))


def _btts_rate(matches: List[Match]) -> float:
    if not matches:
        return 0.5
    n = sum(1 for m in matches if m.home_score > 0 and m.away_score > 0)
    return n / float(len(matches))


def _form_vs_strong(
    db: Session, team_id: int, before: datetime.datetime, limit: int = 5
) -> float:
    recent = _recent_finished(db, team_id, before, limit=20)
    if not recent:
        return 0.33

    strong: List[Match] = []
    for m in recent:
        opp_id = m.away_team_id if m.home_team_id == team_id else m.home_team_id
        opp_elo = _team_latest_post_elo(db, opp_id, m.start_time)
        if opp_elo >= 1600.0:
            strong.append(m)
            if len(strong) >= limit:
                break

    if not strong:
        return 0.33
    return _form_points(strong, team_id)


def _h2h_signal(
    db: Session, home_team_id: int, away_team_id: int, before: datetime.datetime, limit: int = 5
) -> Tuple[float, float, float]:
    past = (
        db.query(Match)
        .filter(Match.status.in_(FINISHED_STATUSES))
        .filter(Match.start_time < before)
        .filter(Match.home_score.isnot(None))
        .filter(Match.away_score.isnot(None))
        .filter(
            or_(
                (Match.home_team_id == home_team_id) & (Match.away_team_id == away_team_id),
                (Match.home_team_id == away_team_id) & (Match.away_team_id == home_team_id),
            )
        )
        .order_by(Match.start_time.desc())
        .limit(limit)
        .all()
    )
    if not past:
        return 0.45, 0.25, 2.6

    home_wins = 0
    draws = 0
    total_goals = 0
    for m in past:
        total_goals += (m.home_score or 0) + (m.away_score or 0)
        if m.home_team_id == home_team_id:
            if m.home_score > m.away_score:
                home_wins += 1
            elif m.home_score == m.away_score:
                draws += 1
        else:
            if m.away_score > m.home_score:
                home_wins += 1
            elif m.home_score == m.away_score:
                draws += 1

    n = len(past)
    return home_wins / n, draws / n, total_goals / n


def build_inference_features(db: Session, match: Match) -> Optional[np.ndarray]:
    """Return a 1xN feature matrix for an upcoming/live match."""
    if match.start_time is None:
        return None

    home_elo = _team_pre_match_elo(db, match.home_team_id, match.id)
    if home_elo is None:
        home_elo = _team_latest_post_elo(db, match.home_team_id, match.start_time)

    away_elo = _team_pre_match_elo(db, match.away_team_id, match.id)
    if away_elo is None:
        away_elo = _team_latest_post_elo(db, match.away_team_id, match.start_time)

    before = match.start_time

    home_recent = _recent_finished(db, match.home_team_id, before, limit=10)
    away_recent = _recent_finished(db, match.away_team_id, before, limit=10)
    home_recent_5 = home_recent[:5]
    away_recent_5 = away_recent[:5]

    home_home_5 = _recent_finished_at_venue(db, match.home_team_id, before, is_home=True, limit=5)
    away_away_5 = _recent_finished_at_venue(db, match.away_team_id, before, is_home=False, limit=5)

    home_form_5 = _form_points(home_recent_5, match.home_team_id)
    away_form_5 = _form_points(away_recent_5, match.away_team_id)
    home_home_form_5 = _form_points(home_home_5, match.home_team_id)
    away_away_form_5 = _form_points(away_away_5, match.away_team_id)

    home_goals_for = _goals_avg(home_recent, match.home_team_id, scored=True)
    away_goals_for = _goals_avg(away_recent, match.away_team_id, scored=True)
    home_goals_against = _goals_avg(home_recent, match.home_team_id, scored=False)
    away_goals_against = _goals_avg(away_recent, match.away_team_id, scored=False)

    home_btts = _btts_rate(home_recent)
    away_btts = _btts_rate(away_recent)

    home_strong = _form_vs_strong(db, match.home_team_id, before)
    away_strong = _form_vs_strong(db, match.away_team_id, before)

    home_rest = _rest_days(db, match.home_team_id, before)
    away_rest = _rest_days(db, match.away_team_id, before)

    h2h_home_win_rate, h2h_draw_rate, h2h_avg_goals = _h2h_signal(
        db, match.home_team_id, match.away_team_id, before
    )

    league_dummies = _league_dummy_columns(match.league_id)

    feats: Dict[str, float] = {
        "home_elo_pre": home_elo,
        "away_elo_pre": away_elo,
        "elo_diff": home_elo - away_elo,
        "elo_ratio": home_elo / max(away_elo, 1.0),
        "home_form_points_5": home_form_5,
        "away_form_points_5": away_form_5,
        "form_diff_5": home_form_5 - away_form_5,
        "home_home_form_5": home_home_form_5,
        "away_away_form_5": away_away_form_5,
        "venue_form_diff": home_home_form_5 - away_away_form_5,
        "home_goals_for_avg_10": home_goals_for,
        "away_goals_for_avg_10": away_goals_for,
        "home_goals_against_avg_10": home_goals_against,
        "away_goals_against_avg_10": away_goals_against,
        "home_goal_diff_avg_10": home_goals_for - home_goals_against,
        "away_goal_diff_avg_10": away_goals_for - away_goals_against,
        "home_btts_rate_10": home_btts,
        "away_btts_rate_10": away_btts,
        "home_form_vs_strong_5": home_strong,
        "away_form_vs_strong_5": away_strong,
        "rest_days_diff": home_rest - away_rest,
        "is_weekend": 1.0 if before and before.weekday() >= 5 else 0.0,
        "h2h_home_win_rate": h2h_home_win_rate,
        "h2h_draw_rate": h2h_draw_rate,
        "h2h_avg_goals": h2h_avg_goals,
        **league_dummies,
    }

    return np.array([[feats[col] for col in FEATURE_COLUMNS]], dtype=np.float32)


def _rest_days(db: Session, team_id: int, before: datetime.datetime) -> float:
    last = (
        db.query(Match)
        .filter(Match.status.in_(FINISHED_STATUSES))
        .filter(or_(Match.home_team_id == team_id, Match.away_team_id == team_id))
        .filter(Match.start_time < before)
        .order_by(Match.start_time.desc())
        .first()
    )
    if not last or not last.start_time:
        return 7.0
    delta = before - last.start_time
    return max(0.0, min(30.0, delta.total_seconds() / 86400.0))
