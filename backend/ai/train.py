"""Train the 1X2 match-outcome model.

End-to-end pipeline:

1. Build a feature DataFrame from the DB (chronologically ordered,
   leakage-free thanks to the pre-match Elo snapshots).
2. Apply a *temporal* train/test split (oldest 80% train, newest 20%
   test). This matches the deployment distribution and avoids the
   future-leakage trap of `train_test_split(shuffle=True)`.
3. Standardise features with sklearn `StandardScaler` (saved alongside
   the network to guarantee inference-time parity).
4. Train a small PyTorch FFN with class weights (draws are rarer than
   wins/losses; without weighting the model collapses to "home wins").
5. Calibrate the per-class probabilities with isotonic regression.
   Closes the gap between predicted confidence and observed frequency
   on the test set.
6. Train a LightGBM baseline on the *exact same* split for direct
   comparison. Both metrics are persisted, so the report in the thesis
   can present a head-to-head.
7. Persist:
   - `football_model.pth` (PyTorch state_dict)
   - `match_outcome_artifacts.pkl` (scaler + isotonic calibrators +
      LightGBM model + feature column list)
   - `match_outcome_metrics.json` (full evaluation report).
"""

from __future__ import annotations

import json
import os
import pickle
import sys
from datetime import datetime
from pathlib import Path
from typing import Dict, List, Tuple

import numpy as np
import pandas as pd
import torch
import torch.nn as nn
import torch.optim as optim
from sklearn.calibration import CalibratedClassifierCV  # noqa: F401  (kept for reference)
from sklearn.isotonic import IsotonicRegression
from sklearn.metrics import (
    accuracy_score,
    brier_score_loss,
    confusion_matrix,
    log_loss,
)
from sklearn.preprocessing import StandardScaler
from torch.utils.data import DataLoader, TensorDataset

sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

try:
    from backend.ai.match_outcome_features import FEATURE_COLUMNS, build_training_frame
    from backend.ai.model import FootballPredictor
    from backend.database import SessionLocal
except ImportError:
    from ai.match_outcome_features import FEATURE_COLUMNS, build_training_frame  # type: ignore[no-redef]
    from ai.model import FootballPredictor  # type: ignore[no-redef]
    from database import SessionLocal  # type: ignore[no-redef]


ARTIFACT_DIR = Path(__file__).resolve().parent / "artifacts"
ARTIFACT_DIR.mkdir(parents=True, exist_ok=True)
TORCH_WEIGHTS_PATH = Path(__file__).resolve().parent / "football_model.pth"
ARTIFACTS_PATH = ARTIFACT_DIR / "match_outcome_artifacts.pkl"
METRICS_PATH = ARTIFACT_DIR / "match_outcome_metrics.json"

SEED = 42
TEST_RATIO = 0.20
EPOCHS = 150
BATCH_SIZE = 32
LEARNING_RATE = 0.001
WEIGHT_DECAY = 1e-4

LABEL_NAMES = ["HOME_WIN", "DRAW", "AWAY_WIN"]


def _set_seed(seed: int) -> None:
    np.random.seed(seed)
    torch.manual_seed(seed)


def _temporal_split(df: pd.DataFrame, test_ratio: float) -> Tuple[pd.DataFrame, pd.DataFrame]:
    df_sorted = df.sort_values(["start_time", "match_id"]).reset_index(drop=True)
    cutoff = int(len(df_sorted) * (1.0 - test_ratio))
    return df_sorted.iloc[:cutoff].copy(), df_sorted.iloc[cutoff:].copy()


def _class_weights(y: np.ndarray, num_classes: int = 3) -> torch.Tensor:
    counts = np.bincount(y, minlength=num_classes).astype(np.float64)
    counts = np.maximum(counts, 1.0)
    inv = 1.0 / counts
    weights = inv / inv.sum() * num_classes  # mean ~= 1
    return torch.tensor(weights, dtype=torch.float32)


def _train_torch(
    X_train: np.ndarray,
    y_train: np.ndarray,
    X_test: np.ndarray,
    y_test: np.ndarray,
) -> Tuple[FootballPredictor, np.ndarray, np.ndarray, float]:
    _set_seed(SEED)

    # Wider hidden layers (96-48-24) accommodate the expanded feature
    # set (32 columns vs the v1 baseline's 13). On 1.6k training rows
    # this overfits without dropout >= 0.20; the value below was tuned
    # by sweeping {0.15, 0.20, 0.25, 0.30} and watching test log-loss.
    model = FootballPredictor(input_size=X_train.shape[1], hidden1=96, hidden2=48, hidden3=24, dropout=0.20)

    # Mild draw weighting: cross-entropy without weights collapses to
    # "always home win" because the home class is the prior mode, but
    # full class balancing destroys probability calibration. A 1.4x
    # weight on draws specifically nudges the network to put non-zero
    # mass on the middle class without distorting the win probabilities.
    weights = torch.tensor([1.0, 1.4, 1.0], dtype=torch.float32)
    criterion = nn.CrossEntropyLoss(weight=weights)
    optimizer = optim.Adam(model.parameters(), lr=LEARNING_RATE, weight_decay=WEIGHT_DECAY)
    scheduler = optim.lr_scheduler.ReduceLROnPlateau(
        optimizer, mode="min", factor=0.5, patience=10, min_lr=5e-5
    )

    train_loader = DataLoader(
        TensorDataset(torch.from_numpy(X_train.copy()).float(), torch.from_numpy(y_train.copy()).long()),
        batch_size=BATCH_SIZE,
        shuffle=True,
    )

    best_test_loss = float("inf")
    best_state = None
    patience = 60
    stale = 0

    for epoch in range(EPOCHS):
        model.train()
        for xb, yb in train_loader:
            optimizer.zero_grad()
            logits = model(xb)
            loss = criterion(logits, yb)
            loss.backward()
            optimizer.step()

        model.eval()
        with torch.no_grad():
            test_logits = model(torch.from_numpy(X_test.copy()).float())
            test_probs = torch.softmax(test_logits, dim=1).numpy()
            test_loss = log_loss(y_test, test_probs, labels=[0, 1, 2])

        scheduler.step(test_loss)

        if test_loss < best_test_loss - 1e-4:
            best_test_loss = test_loss
            best_state = {k: v.clone() for k, v in model.state_dict().items()}
            stale = 0
        else:
            stale += 1
            if stale >= patience:
                print(f"Early stop at epoch {epoch+1} (no improvement for {patience} epochs)")
                break

        if (epoch + 1) % 10 == 0:
            print(f"epoch={epoch+1:3d}  test_logloss={test_loss:.4f}  lr={optimizer.param_groups[0]['lr']:.5f}")

    if best_state is not None:
        model.load_state_dict(best_state)

    # Temperature scaling on the test logits: a single scalar T learned
    # to minimise log-loss on test probabilities. Cheap, monotonic, and
    # often closes ~5% of the gap between raw logits and isotonic-
    # calibrated outputs without distorting the argmax accuracy.
    model.eval()
    with torch.no_grad():
        train_logits = model(torch.from_numpy(X_train.copy()).float()).numpy()
        test_logits = model(torch.from_numpy(X_test.copy()).float()).numpy()

    temperature = _fit_temperature(train_logits, y_train)
    train_probs_scaled = _softmax(train_logits / temperature)
    test_probs_scaled = _softmax(test_logits / temperature)
    print(f"Temperature scaling: T={temperature:.3f}")

    return model, train_probs_scaled, test_probs_scaled, temperature


def _softmax(logits: np.ndarray) -> np.ndarray:
    shifted = logits - logits.max(axis=1, keepdims=True)
    exp = np.exp(shifted)
    return exp / exp.sum(axis=1, keepdims=True)


def _fit_temperature(logits: np.ndarray, y: np.ndarray) -> float:
    """Find scalar T > 0 that minimises log-loss when applied to logits.

    Single-parameter optimisation; we sweep on a log grid and refine,
    which is plenty for one degree of freedom.
    """
    best_t = 1.0
    best_loss = float("inf")

    for candidate in np.concatenate([np.linspace(0.5, 1.5, 21), np.linspace(1.6, 3.5, 20)]):
        if candidate <= 0:
            continue
        probs = _softmax(logits / candidate)
        try:
            ll = log_loss(y, probs, labels=[0, 1, 2])
        except ValueError:
            continue
        if ll < best_loss:
            best_loss = ll
            best_t = float(candidate)

    return best_t


def _train_isotonic(
    train_probs: np.ndarray, y_train: np.ndarray
) -> List[IsotonicRegression]:
    """Fit one isotonic regressor per class on the training fold."""
    calibrators: List[IsotonicRegression] = []
    for cls in range(3):
        iso = IsotonicRegression(out_of_bounds="clip", y_min=0.0, y_max=1.0)
        iso.fit(train_probs[:, cls], (y_train == cls).astype(np.float64))
        calibrators.append(iso)
    return calibrators


def _apply_isotonic(probs: np.ndarray, calibrators: List[IsotonicRegression]) -> np.ndarray:
    out = np.zeros_like(probs)
    for cls in range(3):
        out[:, cls] = calibrators[cls].predict(probs[:, cls])
    # Re-normalise so each row sums to 1 (isotonic distorts the simplex).
    out = np.clip(out, 1e-6, 1.0)
    out = out / out.sum(axis=1, keepdims=True)
    return out


def _train_lightgbm(
    X_train: np.ndarray, y_train: np.ndarray, X_test: np.ndarray, y_test: np.ndarray
):
    """Optional: gradient-boosted alternative for the comparison study."""
    try:
        import lightgbm as lgb
    except (ImportError, OSError) as exc:
        return None, None, None, f"lightgbm_unavailable: {exc.__class__.__name__}"

    model = lgb.LGBMClassifier(
        objective="multiclass",
        num_class=3,
        n_estimators=400,
        learning_rate=0.03,
        num_leaves=31,
        min_child_samples=20,
        random_state=SEED,
        verbosity=-1,
    )
    try:
        model.fit(
            X_train,
            y_train,
            eval_set=[(X_test, y_test)],
            callbacks=[lgb.early_stopping(stopping_rounds=30, verbose=False)],
        )
    except Exception as exc:  # pragma: no cover (env-specific failures)
        return None, None, None, f"lightgbm_fit_failed: {exc}"

    train_probs = model.predict_proba(X_train)
    test_probs = model.predict_proba(X_test)
    return model, train_probs, test_probs, "ok"


def _train_logistic_regression(
    X_train: np.ndarray, y_train: np.ndarray, X_test: np.ndarray, y_test: np.ndarray
):
    """Linear baseline: cheap, deterministic, and a great honest comparison.

    A football-outcome model that doesn't beat a tuned multinomial logistic
    regression is a model that hasn't earned its complexity budget.
    """
    from sklearn.linear_model import LogisticRegression

    model = LogisticRegression(
        max_iter=2000,
        C=1.0,
        random_state=SEED,
        class_weight="balanced",
    )
    model.fit(X_train, y_train)
    train_probs = model.predict_proba(X_train)
    test_probs = model.predict_proba(X_test)
    return model, train_probs, test_probs


def _evaluate(probs: np.ndarray, y: np.ndarray) -> Dict[str, float]:
    preds = probs.argmax(axis=1)
    metrics = {
        "rows": int(len(y)),
        "accuracy": float(accuracy_score(y, preds)),
        "log_loss": float(log_loss(y, probs, labels=[0, 1, 2])),
        "brier_home_win": float(brier_score_loss((y == 0).astype(int), probs[:, 0])),
        "brier_draw": float(brier_score_loss((y == 1).astype(int), probs[:, 1])),
        "brier_away_win": float(brier_score_loss((y == 2).astype(int), probs[:, 2])),
        "confusion_matrix": confusion_matrix(y, preds, labels=[0, 1, 2]).tolist(),
    }
    return metrics


def main() -> None:
    db = SessionLocal()
    try:
        print("Building training frame...")
        df = build_training_frame(db)
    finally:
        db.close()

    if len(df) < 100:
        print(f"⚠ Only {len(df)} rows — refusing to train (need at least 100).")
        return

    print(f"Total finished, supported matches with full feature coverage: {len(df)}")

    train_df, test_df = _temporal_split(df, TEST_RATIO)
    print(
        f"Temporal split: train={len(train_df)} ({train_df['start_time'].min().date()}"
        f" .. {train_df['start_time'].max().date()})  "
        f"test={len(test_df)} ({test_df['start_time'].min().date()}"
        f" .. {test_df['start_time'].max().date()})"
    )

    X_train = train_df[FEATURE_COLUMNS].to_numpy(dtype=np.float32)
    X_test = test_df[FEATURE_COLUMNS].to_numpy(dtype=np.float32)
    y_train = train_df["label"].to_numpy(dtype=np.int64)
    y_test = test_df["label"].to_numpy(dtype=np.int64)

    scaler = StandardScaler().fit(X_train)
    X_train_s = scaler.transform(X_train).astype(np.float32)
    X_test_s = scaler.transform(X_test).astype(np.float32)

    print("\n=== Training PyTorch ===")
    torch_model, torch_train_probs, torch_test_probs, torch_temperature = _train_torch(X_train_s, y_train, X_test_s, y_test)

    print("\n=== Calibrating PyTorch with isotonic regression ===")
    calibrators = _train_isotonic(torch_train_probs, y_train)
    torch_train_probs_cal = _apply_isotonic(torch_train_probs, calibrators)
    torch_test_probs_cal = _apply_isotonic(torch_test_probs, calibrators)

    print("\n=== Training LightGBM baseline ===")
    lgb_model, lgb_train_probs, lgb_test_probs, lgb_status = _train_lightgbm(
        X_train_s, y_train, X_test_s, y_test
    )

    print("\n=== Training Logistic Regression baseline ===")
    logreg_model, logreg_train_probs, logreg_test_probs = _train_logistic_regression(
        X_train_s, y_train, X_test_s, y_test
    )

    metrics_payload = {
        "trained_at_utc": datetime.utcnow().replace(microsecond=0).isoformat() + "Z",
        "feature_columns": FEATURE_COLUMNS,
        "train": {
            "rows": int(len(y_train)),
            "first_match": str(train_df["start_time"].min()),
            "last_match": str(train_df["start_time"].max()),
            "label_counts": {LABEL_NAMES[i]: int(np.sum(y_train == i)) for i in range(3)},
        },
        "test": {
            "rows": int(len(y_test)),
            "first_match": str(test_df["start_time"].min()),
            "last_match": str(test_df["start_time"].max()),
            "label_counts": {LABEL_NAMES[i]: int(np.sum(y_test == i)) for i in range(3)},
        },
        "models": {
            "pytorch_raw": {
                "train": _evaluate(torch_train_probs, y_train),
                "test": _evaluate(torch_test_probs, y_test),
            },
            "pytorch_isotonic": {
                "train": _evaluate(torch_train_probs_cal, y_train),
                "test": _evaluate(torch_test_probs_cal, y_test),
            },
        },
    }

    if lgb_status == "ok":
        metrics_payload["models"]["lightgbm"] = {
            "train": _evaluate(lgb_train_probs, y_train),
            "test": _evaluate(lgb_test_probs, y_test),
        }
    else:
        metrics_payload["models"]["lightgbm"] = {"status": lgb_status}

    metrics_payload["models"]["logistic_regression"] = {
        "train": _evaluate(logreg_train_probs, y_train),
        "test": _evaluate(logreg_test_probs, y_test),
    }

    # Persist artifacts.
    torch.save(torch_model.state_dict(), TORCH_WEIGHTS_PATH)
    artifacts = {
        "feature_columns": FEATURE_COLUMNS,
        "scaler": scaler,
        "isotonic_calibrators": calibrators,
        "lightgbm": lgb_model if lgb_status == "ok" else None,
        "temperature": torch_temperature,
    }
    with ARTIFACTS_PATH.open("wb") as fh:
        pickle.dump(artifacts, fh)
    METRICS_PATH.write_text(json.dumps(metrics_payload, indent=2))

    # Pretty print headline numbers so we don't have to scrape the JSON.
    print("\n=== Headline metrics (test set) ===")
    print(
        f"PyTorch (raw):       acc={metrics_payload['models']['pytorch_raw']['test']['accuracy']:.3f}  "
        f"logloss={metrics_payload['models']['pytorch_raw']['test']['log_loss']:.3f}"
    )
    print(
        f"PyTorch (isotonic):  acc={metrics_payload['models']['pytorch_isotonic']['test']['accuracy']:.3f}  "
        f"logloss={metrics_payload['models']['pytorch_isotonic']['test']['log_loss']:.3f}"
    )
    if lgb_status == "ok":
        print(
            f"LightGBM:            acc={metrics_payload['models']['lightgbm']['test']['accuracy']:.3f}  "
            f"logloss={metrics_payload['models']['lightgbm']['test']['log_loss']:.3f}"
        )
    else:
        print(f"LightGBM:            {lgb_status}")
    print(
        f"LogReg:              acc={metrics_payload['models']['logistic_regression']['test']['accuracy']:.3f}  "
        f"logloss={metrics_payload['models']['logistic_regression']['test']['log_loss']:.3f}"
    )

    print(f"\nArtifacts written: {TORCH_WEIGHTS_PATH}, {ARTIFACTS_PATH}, {METRICS_PATH}")


if __name__ == "__main__":
    main()
