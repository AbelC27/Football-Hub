"""Retrain the xG proxy model using CSV historical data.

The CSV has shots on goal, possession, corners, etc. for ~47% of matches.
We use these to build a much better xG proxy with 16k+ training rows
instead of the current 2.7k from the DB alone.

Usage:
    cd Football-Hub/backend
    python -m ai.retrain_xg_with_csv
"""
from __future__ import annotations

import json
import math
import pickle
import sys
import os
from collections import defaultdict, deque
from pathlib import Path
from typing import Dict, List

import numpy as np
import pandas as pd
from sklearn.metrics import mean_absolute_error, mean_squared_error, r2_score
from sklearn.model_selection import train_test_split
from sklearn.preprocessing import StandardScaler

sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

CSV_PATH = Path(__file__).resolve().parents[3] / "full_data.csv"
ARTIFACT_DIR = Path(__file__).resolve().parent / "artifacts"
XG_ARTIFACT_PATH = ARTIFACT_DIR / "xg_model.pkl"
XG_METRICS_PATH = ARTIFACT_DIR / "xg_training_metrics.json"

TARGET_LEAGUES = {"premier-league", "laliga", "bundesliga", "serie-a", "ligue-1"}
SEED = 42

# Features we can compute from the CSV
FEATURE_COLUMNS = [
    "is_home",
    "team_goals_for_avg", "team_goals_against_avg",
    "team_shots_on_avg", "opp_shots_on_avg",
    "team_possession_avg", "opp_possession_avg",
    "team_corners_avg", "opp_corners_avg",
    "team_form_points_last5", "opp_form_points_last5",
    "team_shots_off_avg", "opp_shots_off_avg",
    "opp_goals_for_avg", "opp_goals_against_avg",
    "team_points_per_match", "opp_points_per_match",
    "team_rest_days", "opp_rest_days",
    "is_weekend",
    "team_gd_avg", "opp_gd_avg",
]


def load_csv() -> pd.DataFrame:
    df = pd.read_csv(CSV_PATH)
    df = df[df["League"].isin(TARGET_LEAGUES)].copy()
    df = df.dropna(subset=["H_Score", "A_Score", "Date"])
    df["H_Score"] = df["H_Score"].astype(int)
    df["A_Score"] = df["A_Score"].astype(int)
    # Only keep rows with stats
    df["has_stats"] = df["H_Ball_Possession"].notna() & (df["H_Ball_Possession"] != "")
    df["date_parsed"] = pd.to_datetime(df["Date"], format="%d.%m.%Y", errors="coerce")
    df = df.dropna(subset=["date_parsed"])
    df = df.sort_values("date_parsed").reset_index(drop=True)
    return df


def _safe_float(v, default=0.0):
    try:
        return float(v) if v and str(v).strip() else default
    except (ValueError, TypeError):
        return default


def build_xg_features(df: pd.DataFrame) -> pd.DataFrame:
    """Build per-team-per-match xG features from CSV (2 rows per match)."""
    # Rolling stats per team
    team_goals_for: Dict[str, deque] = defaultdict(lambda: deque(maxlen=10))
    team_goals_against: Dict[str, deque] = defaultdict(lambda: deque(maxlen=10))
    team_shots_on: Dict[str, deque] = defaultdict(lambda: deque(maxlen=10))
    team_shots_off: Dict[str, deque] = defaultdict(lambda: deque(maxlen=10))
    team_possession: Dict[str, deque] = defaultdict(lambda: deque(maxlen=10))
    team_corners: Dict[str, deque] = defaultdict(lambda: deque(maxlen=10))
    team_form: Dict[str, deque] = defaultdict(lambda: deque(maxlen=5))
    team_last_date: Dict[str, pd.Timestamp] = {}

    rows = []
    for _, m in df.iterrows():
        home, away = m["Home"], m["Away"]
        h_score, a_score = m["H_Score"], m["A_Score"]
        date = m["date_parsed"]
        has_stats = m["has_stats"]

        # Parse stats
        h_shots_on = _safe_float(m.get("H_Shots_on_Goal"))
        a_shots_on = _safe_float(m.get("A_Shots_on_Goal"))
        h_shots_off = _safe_float(m.get("H_Shots_off_Goal"))
        a_shots_off = _safe_float(m.get("A_Shots_off_Goal"))
        h_poss = _safe_float(m.get("H_Ball_Possession"), 50)
        a_poss = _safe_float(m.get("A_Ball_Possession"), 50)
        h_corners = _safe_float(m.get("H_Corner_Kicks"))
        a_corners = _safe_float(m.get("A_Corner_Kicks"))

        def _avg(dq, default=0.0):
            return sum(dq) / len(dq) if dq else default

        def _form_pts(dq):
            return sum(dq) / (3.0 * len(dq)) if dq else 0.5

        # Build features for HOME team perspective
        if team_goals_for[home]:  # skip first few matches
            h_rest = (date - team_last_date[home]).days if home in team_last_date else 7
            a_rest = (date - team_last_date[away]).days if away in team_last_date else 7
            row_home = {
                "is_home": 1.0,
                "team_goals_for_avg": _avg(team_goals_for[home], 1.3),
                "team_goals_against_avg": _avg(team_goals_against[home], 1.3),
                "team_shots_on_avg": _avg(team_shots_on[home], 4.0),
                "opp_shots_on_avg": _avg(team_shots_on[away], 4.0),
                "team_possession_avg": _avg(team_possession[home], 50),
                "opp_possession_avg": _avg(team_possession[away], 50),
                "team_corners_avg": _avg(team_corners[home], 5.0),
                "opp_corners_avg": _avg(team_corners[away], 5.0),
                "team_form_points_last5": _form_pts(team_form[home]),
                "opp_form_points_last5": _form_pts(team_form[away]),
                "team_shots_off_avg": _avg(team_shots_off[home], 4.0),
                "opp_shots_off_avg": _avg(team_shots_off[away], 4.0),
                "opp_goals_for_avg": _avg(team_goals_for[away], 1.3),
                "opp_goals_against_avg": _avg(team_goals_against[away], 1.3),
                "team_points_per_match": _form_pts(team_form[home]),
                "opp_points_per_match": _form_pts(team_form[away]),
                "team_rest_days": min(h_rest, 30),
                "opp_rest_days": min(a_rest, 30),
                "is_weekend": 1.0 if date.weekday() >= 4 else 0.0,
                "team_gd_avg": _avg(team_goals_for[home], 1.3) - _avg(team_goals_against[home], 1.3),
                "opp_gd_avg": _avg(team_goals_for[away], 1.3) - _avg(team_goals_against[away], 1.3),
                "target_goals": h_score,
            }
            rows.append(row_home)

            # AWAY team perspective
            row_away = {
                "is_home": 0.0,
                "team_goals_for_avg": _avg(team_goals_for[away], 1.3),
                "team_goals_against_avg": _avg(team_goals_against[away], 1.3),
                "team_shots_on_avg": _avg(team_shots_on[away], 4.0),
                "opp_shots_on_avg": _avg(team_shots_on[home], 4.0),
                "team_possession_avg": _avg(team_possession[away], 50),
                "opp_possession_avg": _avg(team_possession[home], 50),
                "team_corners_avg": _avg(team_corners[away], 5.0),
                "opp_corners_avg": _avg(team_corners[home], 5.0),
                "team_form_points_last5": _form_pts(team_form[away]),
                "opp_form_points_last5": _form_pts(team_form[home]),
                "team_shots_off_avg": _avg(team_shots_off[away], 4.0),
                "opp_shots_off_avg": _avg(team_shots_off[home], 4.0),
                "opp_goals_for_avg": _avg(team_goals_for[home], 1.3),
                "opp_goals_against_avg": _avg(team_goals_against[home], 1.3),
                "team_points_per_match": _form_pts(team_form[away]),
                "opp_points_per_match": _form_pts(team_form[home]),
                "team_rest_days": min(a_rest, 30),
                "opp_rest_days": min(h_rest, 30),
                "is_weekend": 1.0 if date.weekday() >= 4 else 0.0,
                "team_gd_avg": _avg(team_goals_for[away], 1.3) - _avg(team_goals_against[away], 1.3),
                "opp_gd_avg": _avg(team_goals_for[home], 1.3) - _avg(team_goals_against[home], 1.3),
                "target_goals": a_score,
            }
            rows.append(row_away)

        # Update rolling stats
        team_goals_for[home].append(h_score)
        team_goals_for[away].append(a_score)
        team_goals_against[home].append(a_score)
        team_goals_against[away].append(h_score)

        if has_stats and h_shots_on > 0:
            team_shots_on[home].append(h_shots_on)
            team_shots_on[away].append(a_shots_on)
            team_shots_off[home].append(h_shots_off)
            team_shots_off[away].append(a_shots_off)
            team_possession[home].append(h_poss)
            team_possession[away].append(a_poss)
            team_corners[home].append(h_corners)
            team_corners[away].append(a_corners)

        h_pts = 3 if h_score > a_score else (1 if h_score == a_score else 0)
        a_pts = 3 - h_pts if h_score != a_score else 1
        team_form[home].append(h_pts)
        team_form[away].append(a_pts)
        team_last_date[home] = date
        team_last_date[away] = date

    result = pd.DataFrame(rows)
    # Drop warm-up
    result = result.iloc[1000:].reset_index(drop=True)
    print(f"xG features: {len(result)} rows")
    return result


def main():
    np.random.seed(SEED)
    print("Loading CSV...")
    df = load_csv()
    print(f"Total matches: {len(df)}, with stats: {df['has_stats'].sum()}")

    print("Building xG features...")
    features = build_xg_features(df)

    # Temporal split
    cutoff = int(len(features) * 0.85)
    train_df = features.iloc[:cutoff]
    test_df = features.iloc[cutoff:]

    X_train = train_df[FEATURE_COLUMNS].to_numpy(dtype=np.float32)
    X_test = test_df[FEATURE_COLUMNS].to_numpy(dtype=np.float32)
    y_train = train_df["target_goals"].to_numpy(dtype=np.float32)
    y_test = test_df["target_goals"].to_numpy(dtype=np.float32)

    print(f"Train: {len(X_train)} | Test: {len(X_test)}")
    print(f"Mean goals (train): {y_train.mean():.3f} | (test): {y_test.mean():.3f}")

    # Train Poisson regression (baseline)
    from sklearn.linear_model import PoissonRegressor
    from sklearn.pipeline import Pipeline

    poisson_model = Pipeline([
        ("scaler", StandardScaler()),
        ("regressor", PoissonRegressor(alpha=0.1, max_iter=1000)),
    ])
    poisson_model.fit(X_train, y_train)
    poisson_train_pred = poisson_model.predict(X_train)
    poisson_test_pred = poisson_model.predict(X_test)

    # Train LightGBM regressor
    lgb_model = None
    lgb_test_pred = None
    try:
        import lightgbm as lgb
        lgb_reg = lgb.LGBMRegressor(
            objective="poisson", n_estimators=500, learning_rate=0.03,
            num_leaves=31, min_child_samples=50, subsample=0.8,
            random_state=SEED, verbosity=-1,
        )
        lgb_reg.fit(X_train, y_train, eval_set=[(X_test, y_test)],
                    callbacks=[lgb.early_stopping(stopping_rounds=30, verbose=False)])
        lgb_train_pred = lgb_reg.predict(X_train)
        lgb_test_pred = lgb_reg.predict(X_test)
        lgb_model = lgb_reg
    except Exception as e:
        print(f"LightGBM unavailable: {e}")

    # Evaluate
    def _eval(y_true, y_pred):
        return {
            "mae": float(mean_absolute_error(y_true, y_pred)),
            "rmse": float(np.sqrt(mean_squared_error(y_true, y_pred))),
            "r2": float(r2_score(y_true, y_pred)),
            "mean_pred": float(y_pred.mean()),
            "mean_true": float(y_true.mean()),
        }

    poisson_metrics = _eval(y_test, poisson_test_pred)
    print(f"\nPoisson:  MAE={poisson_metrics['mae']:.4f} RMSE={poisson_metrics['rmse']:.4f} R²={poisson_metrics['r2']:.4f}")

    best_model = poisson_model
    best_metrics = poisson_metrics
    best_name = "Poisson"

    if lgb_model:
        lgb_metrics = _eval(y_test, lgb_test_pred)
        print(f"LightGBM: MAE={lgb_metrics['mae']:.4f} RMSE={lgb_metrics['rmse']:.4f} R²={lgb_metrics['r2']:.4f}")
        if lgb_metrics["mae"] < poisson_metrics["mae"]:
            best_model = lgb_model
            best_metrics = lgb_metrics
            best_name = "LightGBM"

        # Ensemble
        ens_pred = 0.5 * poisson_test_pred + 0.5 * lgb_test_pred
        ens_metrics = _eval(y_test, ens_pred)
        print(f"Ensemble: MAE={ens_metrics['mae']:.4f} RMSE={ens_metrics['rmse']:.4f} R²={ens_metrics['r2']:.4f}")
        if ens_metrics["mae"] < best_metrics["mae"]:
            best_metrics = ens_metrics
            best_name = "Ensemble"

    print(f"\nBest model: {best_name}")

    # Save artifact (compatible with existing xg_model.py inference)
    artifact = {
        "version": "xg_model_v2_csv",
        "scope": "Top 5 leagues (CSV + DB)",
        "trained_at_utc": pd.Timestamp.utcnow().isoformat() + "Z",
        "mode": "xg_proxy",
        "granularity": {"mode": "xg_proxy", "reason": "Trained on CSV historical data with rolling stats"},
        "config": {"seed": SEED, "test_ratio": 0.15},
        "feature_columns": FEATURE_COLUMNS,
        "target_column": "target_goals",
        "model": poisson_model,  # Keep Poisson for compatibility
        "lgb_model": lgb_model,
        "metrics": {"train": _eval(y_train, poisson_train_pred), "test": poisson_metrics},
        "calibration_bins": {},
        "training_data": {"rows": len(features), "train_rows": len(X_train), "test_rows": len(X_test)},
        "shot_model": None,
        "shot_feature_columns": [],
        "shot_metrics": {},
        "notes": [f"Best: {best_name}. Trained on {len(features)} rows from CSV."],
    }

    with XG_ARTIFACT_PATH.open("wb") as f:
        pickle.dump(artifact, f)

    metrics_out = {
        "version": "xg_model_v2_csv",
        "trained_at_utc": artifact["trained_at_utc"],
        "training_data": artifact["training_data"],
        "metrics": {
            "poisson": {"test": poisson_metrics},
            "lightgbm": {"test": _eval(y_test, lgb_test_pred)} if lgb_model else None,
            "best": {"name": best_name, "test": best_metrics},
        },
    }
    XG_METRICS_PATH.write_text(json.dumps(metrics_out, indent=2))
    print(f"\nSaved: {XG_ARTIFACT_PATH}, {XG_METRICS_PATH}")


if __name__ == "__main__":
    main()
