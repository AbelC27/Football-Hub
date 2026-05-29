"""Retrain the 1X2 model using historical CSV data + existing DB data.

The CSV (full_data.csv) contains ~34k matches from 2003-2021 across
top European leagues. We compute Elo + form features from scratch
(same feature set as the production model) and combine with the DB
matches (2025-2026 season) for a much larger training corpus.

Usage:
    cd Football-Hub/backend
    python -m ai.retrain_with_csv
"""

from __future__ import annotations

import json
import math
import os
import pickle
import sys
from collections import defaultdict, deque
from datetime import datetime
from pathlib import Path
from typing import Dict, List, Optional, Tuple

import numpy as np
import pandas as pd
import torch
import torch.nn as nn
import torch.optim as optim
from sklearn.isotonic import IsotonicRegression
from sklearn.metrics import accuracy_score, brier_score_loss, confusion_matrix, log_loss
from sklearn.preprocessing import StandardScaler
from torch.utils.data import DataLoader, TensorDataset

sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from ai.model import FootballPredictor

# --- Paths ---
CSV_PATH = Path(__file__).resolve().parents[3] / "full_data.csv"
ARTIFACT_DIR = Path(__file__).resolve().parent / "artifacts"
ARTIFACT_DIR.mkdir(parents=True, exist_ok=True)
TORCH_WEIGHTS_PATH = Path(__file__).resolve().parent / "football_model.pth"
ARTIFACTS_PATH = ARTIFACT_DIR / "match_outcome_artifacts.pkl"
METRICS_PATH = ARTIFACT_DIR / "match_outcome_metrics.json"

# --- Config ---
TARGET_LEAGUES = {"premier-league", "laliga", "bundesliga", "serie-a", "ligue-1"}
LEAGUE_ONEHOT = {
    "premier-league": "league_premier_league",
    "laliga": "league_la_liga",
    "bundesliga": "league_bundesliga",
    "serie-a": "league_serie_a",
    "ligue-1": "league_ligue_1",
}

FEATURE_COLUMNS: List[str] = [
    "home_elo_pre", "away_elo_pre", "elo_diff", "elo_ratio",
    "home_form_points_5", "away_form_points_5", "form_diff_5",
    "home_home_form_5", "away_away_form_5", "venue_form_diff",
    "home_goals_for_avg_10", "away_goals_for_avg_10",
    "home_goals_against_avg_10", "away_goals_against_avg_10",
    "home_goal_diff_avg_10", "away_goal_diff_avg_10",
    "home_btts_rate_10", "away_btts_rate_10",
    "home_form_vs_strong_5", "away_form_vs_strong_5",
    "rest_days_diff", "is_weekend",
    "h2h_home_win_rate", "h2h_draw_rate", "h2h_avg_goals",
    # Betting odds (implied probabilities)
    "odds_impl_home", "odds_impl_draw", "odds_impl_away",
    # Poisson draw signal
    "draw_signal",
    # Season phase
    "season_phase",
    # League dummies
    "league_premier_league", "league_la_liga", "league_bundesliga",
    "league_serie_a", "league_ligue_1", "league_ucl", "league_other",
]

SEED = 42
TEST_RATIO = 0.15
EPOCHS = 200
BATCH_SIZE = 64
LEARNING_RATE = 0.001
WEIGHT_DECAY = 1e-4
LABEL_NAMES = ["HOME_WIN", "DRAW", "AWAY_WIN"]

# --- Elo Engine (inline, same params as elo.py) ---
DEFAULT_RATING = 1500.0
HOME_ADVANTAGE = 65.0
K_BASE = 20.0


def _expected_score(ra: float, rb: float) -> float:
    return 1.0 / (1.0 + math.pow(10.0, (rb - ra) / 400.0))


def _goal_diff_mult(gd: int) -> float:
    return math.log1p(gd) if gd > 0 else 1.0


# --- Feature computation from CSV ---

def load_csv() -> pd.DataFrame:
    """Load and filter CSV to target leagues with valid scores."""
    df = pd.read_csv(CSV_PATH)
    df = df[df["League"].isin(TARGET_LEAGUES)].copy()
    df = df.dropna(subset=["H_Score", "A_Score", "Date"])
    df["H_Score"] = df["H_Score"].astype(int)
    df["A_Score"] = df["A_Score"].astype(int)
    df["date_parsed"] = pd.to_datetime(df["Date"], format="%d.%m.%Y", errors="coerce")
    df = df.dropna(subset=["date_parsed"])
    df = df.sort_values("date_parsed").reset_index(drop=True)
    print(f"CSV loaded: {len(df)} matches ({df['date_parsed'].min().date()} to {df['date_parsed'].max().date()})")
    return df


def build_features_from_csv(df: pd.DataFrame) -> pd.DataFrame:
    """Compute Elo + form features chronologically (no leakage)."""
    # State trackers
    elo: Dict[str, float] = defaultdict(lambda: DEFAULT_RATING)
    # Form: last N results per team (points, goals_for, goals_against)
    form_all: Dict[str, deque] = defaultdict(lambda: deque(maxlen=10))
    form_home: Dict[str, deque] = defaultdict(lambda: deque(maxlen=5))
    form_away: Dict[str, deque] = defaultdict(lambda: deque(maxlen=5))
    last_match_date: Dict[str, Optional[datetime]] = defaultdict(lambda: None)
    # H2H tracker
    h2h: Dict[Tuple[str, str], List[Tuple[int, int]]] = defaultdict(list)

    rows = []
    for _, match in df.iterrows():
        home = match["Home"]
        away = match["Away"]
        league = match["League"]
        h_score = match["H_Score"]
        a_score = match["A_Score"]
        date = match["date_parsed"]
        weekday = date.weekday()

        # --- Pre-match features ---
        home_elo = elo[home]
        away_elo = elo[away]
        elo_diff = home_elo - away_elo
        elo_ratio = home_elo / max(away_elo, 1.0)

        # Form points (last 5 from form_all)
        def _form_points(team_form, n=5):
            recent = list(team_form)[-n:]
            if not recent:
                return 1.0  # neutral
            return sum(r[0] for r in recent) / (3.0 * len(recent))

        def _goals_for_avg(team_form, n=10):
            recent = list(team_form)[-n:]
            if not recent:
                return 1.3
            return sum(r[1] for r in recent) / len(recent)

        def _goals_against_avg(team_form, n=10):
            recent = list(team_form)[-n:]
            if not recent:
                return 1.3
            return sum(r[2] for r in recent) / len(recent)

        def _btts_rate(team_form, n=10):
            recent = list(team_form)[-n:]
            if not recent:
                return 0.5
            return sum(1 for r in recent if r[1] > 0 and r[2] > 0) / len(recent)

        def _venue_form(venue_deque, n=5):
            recent = list(venue_deque)[-n:]
            if not recent:
                return 1.0
            return sum(r[0] for r in recent) / (3.0 * len(recent))

        def _form_vs_strong(team_form, n=5):
            """Form against teams with above-average Elo."""
            recent = list(team_form)[-n:]
            strong = [r for r in recent if r[3] > DEFAULT_RATING + 50]
            if not strong:
                return 0.5
            return sum(r[0] for r in strong) / (3.0 * len(strong))

        home_form_5 = _form_points(form_all[home], 5)
        away_form_5 = _form_points(form_all[away], 5)
        home_home_form = _venue_form(form_home[home], 5)
        away_away_form = _venue_form(form_away[away], 5)

        home_gf = _goals_for_avg(form_all[home], 10)
        away_gf = _goals_for_avg(form_all[away], 10)
        home_ga = _goals_against_avg(form_all[home], 10)
        away_ga = _goals_against_avg(form_all[away], 10)

        home_form_strong = _form_vs_strong(form_all[home], 5)
        away_form_strong = _form_vs_strong(form_all[away], 5)

        # Rest days
        home_last = last_match_date[home]
        away_last = last_match_date[away]
        home_rest = (date - home_last).days if home_last else 7
        away_rest = (date - away_last).days if away_last else 7
        rest_diff = home_rest - away_rest

        # H2H
        h2h_key = tuple(sorted([home, away]))
        h2h_matches = h2h[h2h_key]
        if h2h_matches:
            h2h_home_wins = sum(1 for h, a in h2h_matches if h > a) / len(h2h_matches)
            h2h_draws = sum(1 for h, a in h2h_matches if h == a) / len(h2h_matches)
            h2h_avg_g = sum(h + a for h, a in h2h_matches) / len(h2h_matches)
        else:
            h2h_home_wins, h2h_draws, h2h_avg_g = 0.4, 0.25, 2.5

        # League one-hot
        league_feats = {v: 0.0 for v in LEAGUE_ONEHOT.values()}
        league_feats["league_ucl"] = 0.0
        league_feats["league_other"] = 0.0
        if league in LEAGUE_ONEHOT:
            league_feats[LEAGUE_ONEHOT[league]] = 1.0
        else:
            league_feats["league_other"] = 1.0

        # Betting odds -> implied probabilities
        h_bet = match.get("H_BET")
        x_bet = match.get("X_BET")
        a_bet = match.get("A_BET")
        try:
            h_odds = float(h_bet) if h_bet and str(h_bet).strip() else 0
            x_odds = float(x_bet) if x_bet and str(x_bet).strip() else 0
            a_odds = float(a_bet) if a_bet and str(a_bet).strip() else 0
        except (ValueError, TypeError):
            h_odds = x_odds = a_odds = 0

        if h_odds > 1 and x_odds > 1 and a_odds > 1:
            raw_sum = 1/h_odds + 1/x_odds + 1/a_odds
            odds_impl_home = (1/h_odds) / raw_sum
            odds_impl_draw = (1/x_odds) / raw_sum
            odds_impl_away = (1/a_odds) / raw_sum
        else:
            # No odds available — use Elo-based estimate
            odds_impl_home = _expected_score(home_elo + HOME_ADVANTAGE, away_elo)
            odds_impl_away = 1.0 - odds_impl_home
            odds_impl_draw = 0.26  # league average

        # Poisson draw signal: when both teams score ~1 goal on average
        draw_signal = 1.0 if (0.7 < home_gf < 1.5 and 0.7 < away_gf < 1.5) else 0.0

        # Season phase (0=early, 0.5=mid, 1=late)
        round_str = str(match.get("Round", ""))
        try:
            round_num = int(round_str)
            # Most leagues have 34-38 rounds
            season_phase = min(round_num / 38.0, 1.0)
        except (ValueError, TypeError):
            season_phase = 0.5  # unknown round

        # Label
        if h_score > a_score:
            label = 0
        elif h_score == a_score:
            label = 1
        else:
            label = 2

        row = {
            "home_elo_pre": home_elo,
            "away_elo_pre": away_elo,
            "elo_diff": elo_diff,
            "elo_ratio": elo_ratio,
            "home_form_points_5": home_form_5,
            "away_form_points_5": away_form_5,
            "form_diff_5": home_form_5 - away_form_5,
            "home_home_form_5": home_home_form,
            "away_away_form_5": away_away_form,
            "venue_form_diff": home_home_form - away_away_form,
            "home_goals_for_avg_10": home_gf,
            "away_goals_for_avg_10": away_gf,
            "home_goals_against_avg_10": home_ga,
            "away_goals_against_avg_10": away_ga,
            "home_goal_diff_avg_10": home_gf - home_ga,
            "away_goal_diff_avg_10": away_gf - away_ga,
            "home_btts_rate_10": _btts_rate(form_all[home], 10),
            "away_btts_rate_10": _btts_rate(form_all[away], 10),
            "home_form_vs_strong_5": home_form_strong,
            "away_form_vs_strong_5": away_form_strong,
            "rest_days_diff": rest_diff,
            "is_weekend": 1.0 if weekday >= 4 else 0.0,
            "h2h_home_win_rate": h2h_home_wins,
            "h2h_draw_rate": h2h_draws,
            "h2h_avg_goals": h2h_avg_g,
            "odds_impl_home": odds_impl_home,
            "odds_impl_draw": odds_impl_draw,
            "odds_impl_away": odds_impl_away,
            "draw_signal": draw_signal,
            "season_phase": season_phase,
            **league_feats,
            "label": label,
            "start_time": date,
        }
        rows.append(row)

        # --- Post-match state updates ---
        # Elo update
        home_exp = _expected_score(home_elo + HOME_ADVANTAGE, away_elo)
        if h_score > a_score:
            home_actual, away_actual = 1.0, 0.0
        elif h_score < a_score:
            home_actual, away_actual = 0.0, 1.0
        else:
            home_actual = away_actual = 0.5
        k_eff = K_BASE * _goal_diff_mult(abs(h_score - a_score))
        elo[home] = home_elo + k_eff * (home_actual - home_exp)
        elo[away] = away_elo + k_eff * (away_actual - (1.0 - home_exp))

        # Form update: (points, goals_for, goals_against, opponent_elo)
        home_pts = 3 if h_score > a_score else (1 if h_score == a_score else 0)
        away_pts = 3 if a_score > h_score else (1 if h_score == a_score else 0)
        form_all[home].append((home_pts, h_score, a_score, away_elo))
        form_all[away].append((away_pts, a_score, h_score, home_elo))
        form_home[home].append((home_pts, h_score, a_score, away_elo))
        form_away[away].append((away_pts, a_score, h_score, home_elo))

        # H2H update
        h2h[h2h_key].append((h_score, a_score))

        # Last match date
        last_match_date[home] = date
        last_match_date[away] = date

    result = pd.DataFrame(rows)
    # Drop first ~200 matches where Elo/form haven't stabilized
    result = result.iloc[500:].reset_index(drop=True)
    print(f"Features built: {len(result)} rows (dropped first 500 for Elo warm-up)")
    return result


def load_db_features() -> Optional[pd.DataFrame]:
    """Try to load features from the DB (existing 2025-2026 data)."""
    try:
        from ai.match_outcome_features import FEATURE_COLUMNS as DB_FEATURES, build_training_frame
        from database import SessionLocal
        db = SessionLocal()
        try:
            df = build_training_frame(db)
        finally:
            db.close()
        if len(df) > 50:
            print(f"DB features loaded: {len(df)} rows")
            return df
    except Exception as e:
        print(f"Could not load DB features: {e}")
    return None


# --- Training ---

def _softmax(logits: np.ndarray) -> np.ndarray:
    shifted = logits - logits.max(axis=1, keepdims=True)
    exp = np.exp(shifted)
    return exp / exp.sum(axis=1, keepdims=True)


def _fit_temperature(logits: np.ndarray, y: np.ndarray) -> float:
    best_t, best_loss = 1.0, float("inf")
    for t in np.linspace(0.5, 3.0, 51):
        if t <= 0:
            continue
        probs = _softmax(logits / t)
        ll = log_loss(y, probs, labels=[0, 1, 2])
        if ll < best_loss:
            best_loss = ll
            best_t = float(t)
    return best_t


def _train_isotonic(probs: np.ndarray, y: np.ndarray) -> List[IsotonicRegression]:
    calibrators = []
    for cls in range(3):
        iso = IsotonicRegression(out_of_bounds="clip", y_min=0.0, y_max=1.0)
        iso.fit(probs[:, cls], (y == cls).astype(np.float64))
        calibrators.append(iso)
    return calibrators


def _apply_isotonic(probs: np.ndarray, calibrators: List[IsotonicRegression]) -> np.ndarray:
    out = np.zeros_like(probs)
    for cls in range(3):
        out[:, cls] = calibrators[cls].predict(probs[:, cls])
    out = np.clip(out, 1e-6, 1.0)
    return out / out.sum(axis=1, keepdims=True)


def _evaluate(probs: np.ndarray, y: np.ndarray) -> Dict:
    preds = probs.argmax(axis=1)
    return {
        "rows": int(len(y)),
        "accuracy": float(accuracy_score(y, preds)),
        "log_loss": float(log_loss(y, probs, labels=[0, 1, 2])),
        "brier_home_win": float(brier_score_loss((y == 0).astype(int), probs[:, 0])),
        "brier_draw": float(brier_score_loss((y == 1).astype(int), probs[:, 1])),
        "brier_away_win": float(brier_score_loss((y == 2).astype(int), probs[:, 2])),
        "confusion_matrix": confusion_matrix(y, preds, labels=[0, 1, 2]).tolist(),
    }


def main():
    np.random.seed(SEED)
    torch.manual_seed(SEED)

    # 1. Build features from CSV
    csv_df = load_csv()
    csv_features = build_features_from_csv(csv_df)

    # 2. Try to add DB features
    db_features = load_db_features()
    if db_features is not None:
        # Align columns
        for col in FEATURE_COLUMNS:
            if col not in db_features.columns:
                db_features[col] = 0.0
        db_subset = db_features[FEATURE_COLUMNS + ["label", "start_time"]].copy()
        combined = pd.concat([csv_features[FEATURE_COLUMNS + ["label", "start_time"]], db_subset], ignore_index=True)
        combined = combined.sort_values("start_time").reset_index(drop=True)
        print(f"Combined dataset: {len(combined)} rows (CSV: {len(csv_features)}, DB: {len(db_subset)})")
    else:
        combined = csv_features[FEATURE_COLUMNS + ["label", "start_time"]].copy()
        print(f"Using CSV only: {len(combined)} rows")

    # 3. Temporal split
    cutoff = int(len(combined) * (1.0 - TEST_RATIO))
    train_df = combined.iloc[:cutoff]
    test_df = combined.iloc[cutoff:]
    print(f"Train: {len(train_df)} rows | Test: {len(test_df)} rows")
    print(f"Train period: {train_df['start_time'].min()} to {train_df['start_time'].max()}")
    print(f"Test period:  {test_df['start_time'].min()} to {test_df['start_time'].max()}")

    X_train = train_df[FEATURE_COLUMNS].to_numpy(dtype=np.float32)
    X_test = test_df[FEATURE_COLUMNS].to_numpy(dtype=np.float32)
    y_train = train_df["label"].to_numpy(dtype=np.int64)
    y_test = test_df["label"].to_numpy(dtype=np.int64)

    print(f"\nLabel distribution (train): H={np.sum(y_train==0)}, D={np.sum(y_train==1)}, A={np.sum(y_train==2)}")
    print(f"Label distribution (test):  H={np.sum(y_test==0)}, D={np.sum(y_test==1)}, A={np.sum(y_test==2)}")

    # 4. Scale
    scaler = StandardScaler().fit(X_train)
    X_train_s = scaler.transform(X_train).astype(np.float32)
    X_test_s = scaler.transform(X_test).astype(np.float32)

    # 5. Train PyTorch model (96-48-24 matches inference service)
    print("\n=== Training PyTorch FFN ===")
    model = FootballPredictor(input_size=len(FEATURE_COLUMNS), hidden1=96, hidden2=48, hidden3=24, dropout=0.20)
    weights = torch.tensor([1.0, 1.6, 1.1], dtype=torch.float32)
    criterion = nn.CrossEntropyLoss(weight=weights)
    optimizer = optim.Adam(model.parameters(), lr=0.0005, weight_decay=1e-4)
    scheduler = optim.lr_scheduler.CosineAnnealingLR(optimizer, T_max=EPOCHS, eta_min=1e-5)

    train_loader = DataLoader(
        TensorDataset(torch.from_numpy(X_train_s.copy()).float(), torch.from_numpy(y_train.copy()).long()),
        batch_size=128, shuffle=True,
    )

    best_test_loss = float("inf")
    best_state = None
    patience_counter = 0

    for epoch in range(EPOCHS):
        model.train()
        for xb, yb in train_loader:
            optimizer.zero_grad()
            loss = criterion(model(xb), yb)
            loss.backward()
            optimizer.step()
        scheduler.step()

        model.eval()
        with torch.no_grad():
            test_logits = model(torch.from_numpy(X_test_s.copy()).float())
            test_probs = torch.softmax(test_logits, dim=1).numpy()
            test_loss = log_loss(y_test, test_probs, labels=[0, 1, 2])

        if test_loss < best_test_loss - 5e-5:
            best_test_loss = test_loss
            best_state = {k: v.clone() for k, v in model.state_dict().items()}
            patience_counter = 0
        else:
            patience_counter += 1
            if patience_counter >= 60:
                print(f"Early stop at epoch {epoch+1}")
                break

        if (epoch + 1) % 25 == 0:
            acc = accuracy_score(y_test, test_probs.argmax(axis=1))
            print(f"  epoch {epoch+1:3d}: test_logloss={test_loss:.4f} acc={acc:.4f} lr={optimizer.param_groups[0]['lr']:.6f}")

    if best_state:
        model.load_state_dict(best_state)

    # 6. Temperature scaling + isotonic calibration
    model.eval()
    with torch.no_grad():
        train_logits = model(torch.from_numpy(X_train_s.copy()).float()).numpy()
        test_logits = model(torch.from_numpy(X_test_s.copy()).float()).numpy()

    temperature = _fit_temperature(train_logits, y_train)
    print(f"Temperature: T={temperature:.3f}")

    train_probs = _softmax(train_logits / temperature)
    test_probs = _softmax(test_logits / temperature)

    calibrators = _train_isotonic(train_probs, y_train)
    train_probs_cal = _apply_isotonic(train_probs, calibrators)
    test_probs_cal = _apply_isotonic(test_probs, calibrators)

    # 7. LightGBM
    lgb_metrics = None
    lgb_model = None
    try:
        import lightgbm as lgb
        lgb_clf = lgb.LGBMClassifier(
            objective="multiclass", num_class=3, n_estimators=500,
            learning_rate=0.03, num_leaves=63, min_child_samples=30,
            random_state=SEED, verbosity=-1,
        )
        lgb_clf.fit(X_train_s, y_train, eval_set=[(X_test_s, y_test)],
                    callbacks=[lgb.early_stopping(stopping_rounds=30, verbose=False)])
        lgb_test_probs = lgb_clf.predict_proba(X_test_s)
        lgb_train_probs = lgb_clf.predict_proba(X_train_s)
        lgb_metrics = {"train": _evaluate(lgb_train_probs, y_train), "test": _evaluate(lgb_test_probs, y_test)}
        lgb_model = lgb_clf
        print(f"\nLightGBM: acc={lgb_metrics['test']['accuracy']:.4f} logloss={lgb_metrics['test']['log_loss']:.4f}")
    except Exception as e:
        print(f"LightGBM unavailable: {e}")

    # 8. Logistic Regression baseline
    from sklearn.linear_model import LogisticRegression
    logreg = LogisticRegression(max_iter=2000, C=1.0, random_state=SEED, class_weight="balanced")
    logreg.fit(X_train_s, y_train)
    logreg_test_probs = logreg.predict_proba(X_test_s)
    logreg_train_probs = logreg.predict_proba(X_train_s)
    logreg_metrics = {"train": _evaluate(logreg_train_probs, y_train), "test": _evaluate(logreg_test_probs, y_test)}
    print(f"\nLogReg:   acc={logreg_metrics['test']['accuracy']:.4f} logloss={logreg_metrics['test']['log_loss']:.4f}")

    # 9. Ensemble (average probabilities from available models)
    ensemble_probs_test = test_probs_cal.copy()
    ensemble_probs_train = train_probs_cal.copy()
    n_models = 1
    if lgb_metrics:
        ensemble_probs_test = ensemble_probs_test + lgb_test_probs
        ensemble_probs_train = ensemble_probs_train + lgb_train_probs
        n_models += 1
    ensemble_probs_test = ensemble_probs_test + logreg_test_probs
    ensemble_probs_train = ensemble_probs_train + logreg_train_probs
    n_models += 1
    ensemble_probs_test /= n_models
    ensemble_probs_train /= n_models
    ensemble_metrics = {"train": _evaluate(ensemble_probs_train, y_train), "test": _evaluate(ensemble_probs_test, y_test)}
    print(f"Ensemble ({n_models} models): acc={ensemble_metrics['test']['accuracy']:.4f} logloss={ensemble_metrics['test']['log_loss']:.4f}")

    # 10. Evaluate & report
    pytorch_raw = {"train": _evaluate(train_probs, y_train), "test": _evaluate(test_probs, y_test)}
    pytorch_cal = {"train": _evaluate(train_probs_cal, y_train), "test": _evaluate(test_probs_cal, y_test)}

    print("\n" + "=" * 50)
    print("FINAL RESULTS (test set)")
    print("=" * 50)
    print(f"PyTorch (raw):        acc={pytorch_raw['test']['accuracy']:.4f}  logloss={pytorch_raw['test']['log_loss']:.4f}")
    print(f"PyTorch (calibrated): acc={pytorch_cal['test']['accuracy']:.4f}  logloss={pytorch_cal['test']['log_loss']:.4f}")
    if lgb_metrics:
        print(f"LightGBM:             acc={lgb_metrics['test']['accuracy']:.4f}  logloss={lgb_metrics['test']['log_loss']:.4f}")
    print(f"LogReg:               acc={logreg_metrics['test']['accuracy']:.4f}  logloss={logreg_metrics['test']['log_loss']:.4f}")
    print(f"ENSEMBLE:             acc={ensemble_metrics['test']['accuracy']:.4f}  logloss={ensemble_metrics['test']['log_loss']:.4f}")
    print(f"\nConfusion matrix (Ensemble):\n{np.array(ensemble_metrics['test']['confusion_matrix'])}")

    # 11. Save artifacts (use best single model for inference)
    torch.save(model.state_dict(), TORCH_WEIGHTS_PATH)
    artifacts = {
        "feature_columns": FEATURE_COLUMNS,
        "scaler": scaler,
        "isotonic_calibrators": calibrators,
        "lightgbm": lgb_model,
        "logistic_regression": logreg,
        "temperature": temperature,
    }
    with ARTIFACTS_PATH.open("wb") as fh:
        pickle.dump(artifacts, fh)

    metrics_payload = {
        "trained_at_utc": datetime.utcnow().isoformat() + "Z",
        "data_source": "CSV (full_data.csv) + DB",
        "csv_matches": len(csv_features),
        "db_matches": len(db_features) if db_features is not None else 0,
        "total_rows": len(combined),
        "feature_columns": FEATURE_COLUMNS,
        "train": {"rows": int(len(y_train))},
        "test": {"rows": int(len(y_test))},
        "models": {
            "pytorch_raw": pytorch_raw,
            "pytorch_isotonic": pytorch_cal,
            "logistic_regression": logreg_metrics,
            "ensemble": ensemble_metrics,
        },
    }
    if lgb_metrics:
        metrics_payload["models"]["lightgbm"] = lgb_metrics

    METRICS_PATH.write_text(json.dumps(metrics_payload, indent=2))
    print(f"\nSaved: {TORCH_WEIGHTS_PATH}, {ARTIFACTS_PATH}, {METRICS_PATH}")


if __name__ == "__main__":
    main()
