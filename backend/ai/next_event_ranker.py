import datetime
import pickle
from pathlib import Path
from typing import Dict, List, Optional, Tuple

import numpy as np
import pandas as pd
from sklearn.linear_model import LogisticRegression
from sklearn.pipeline import Pipeline
from sklearn.preprocessing import StandardScaler

try:
    from backend.ai.next_event_features import FEATURE_COLUMNS, NextEventFeatureBuilder
except ImportError:
    from ai.next_event_features import FEATURE_COLUMNS, NextEventFeatureBuilder


ARTIFACT_DIR = Path(__file__).resolve().parent / "artifacts"
DEFAULT_ARTIFACT_PATH = ARTIFACT_DIR / "next_event_ranker.pkl"
DEFAULT_METRICS_PATH = ARTIFACT_DIR / "next_event_metrics.json"


def split_samples_chronologically(frame: pd.DataFrame, test_ratio: float = 0.2) -> Tuple[pd.DataFrame, pd.DataFrame]:
    if frame.empty:
        return frame.copy(), frame.copy()

    samples = (
        frame[["sample_id", "event_time"]]
        .drop_duplicates()
        .sort_values(["event_time", "sample_id"], ascending=[True, True])
        .reset_index(drop=True)
    )

    sample_count = len(samples)
    if sample_count < 2:
        return frame.copy(), frame.iloc[0:0].copy()

    test_count = max(1, int(round(sample_count * test_ratio)))
    if test_count >= sample_count:
        test_count = 1

    train_ids = set(samples.iloc[:-test_count]["sample_id"].tolist())
    test_ids = set(samples.iloc[-test_count:]["sample_id"].tolist())

    train_frame = frame[frame["sample_id"].isin(train_ids)].copy()
    test_frame = frame[frame["sample_id"].isin(test_ids)].copy()
    return train_frame, test_frame


def train_task_model(frame: pd.DataFrame, feature_columns: List[str]) -> Pipeline:
    if frame.empty:
        raise ValueError("Cannot train model on an empty frame")

    if frame["label"].nunique() < 2:
        raise ValueError("Training frame must contain both positive and negative labels")

    model = Pipeline(
        steps=[
            ("scaler", StandardScaler()),
            (
                "classifier",
                LogisticRegression(
                    max_iter=2000,
                    class_weight="balanced",
                    solver="lbfgs",
                ),
            ),
        ]
    )

    X = frame[feature_columns].to_numpy(dtype=np.float64)
    y = frame["label"].to_numpy(dtype=np.int64)
    model.fit(X, y)
    return model


def _normalize_probabilities(values: np.ndarray) -> np.ndarray:
    if values.size == 0:
        return values

    clipped = np.clip(values.astype(np.float64), 1e-9, None)
    total = float(clipped.sum())
    if total <= 0:
        return np.full_like(clipped, 1.0 / len(clipped), dtype=np.float64)

    return clipped / total


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


def evaluate_ranked_samples(frame: pd.DataFrame, raw_scores: np.ndarray) -> Dict[str, float]:
    if frame.empty:
        return {
            "samples": 0,
            "top1": 0.0,
            "top3": 0.0,
            "log_loss": 0.0,
            "brier": 0.0,
            "ece_10_bin": 0.0,
        }

    eval_frame = frame[["sample_id", "player_id", "label"]].copy().reset_index(drop=True)
    eval_frame["raw_score"] = raw_scores

    top1_hits = 0
    top3_hits = 0
    sample_counter = 0
    losses: List[float] = []

    candidate_probs: List[float] = []
    candidate_labels: List[float] = []

    for sample_id, group in eval_frame.groupby("sample_id"):
        if group.empty:
            continue

        group_probs = _normalize_probabilities(group["raw_score"].to_numpy(dtype=np.float64))
        labels = group["label"].to_numpy(dtype=np.int64)

        true_indices = np.where(labels == 1)[0]
        if len(true_indices) != 1:
            continue

        true_index = int(true_indices[0])
        true_prob = float(group_probs[true_index])

        ordering = np.argsort(-group_probs)
        if ordering[0] == true_index:
            top1_hits += 1

        if true_index in ordering[:3]:
            top3_hits += 1

        losses.append(float(-np.log(np.clip(true_prob, 1e-12, 1.0))))

        candidate_probs.extend(group_probs.tolist())
        candidate_labels.extend(labels.astype(float).tolist())
        sample_counter += 1

    if sample_counter == 0:
        return {
            "samples": 0,
            "top1": 0.0,
            "top3": 0.0,
            "log_loss": 0.0,
            "brier": 0.0,
            "ece_10_bin": 0.0,
        }

    candidate_probs_arr = np.array(candidate_probs, dtype=np.float64)
    candidate_labels_arr = np.array(candidate_labels, dtype=np.float64)

    metrics = {
        "samples": int(sample_counter),
        "top1": float(top1_hits / sample_counter),
        "top3": float(top3_hits / sample_counter),
        "log_loss": float(np.mean(losses) if losses else 0.0),
        "brier": float(np.mean((candidate_probs_arr - candidate_labels_arr) ** 2)),
        "ece_10_bin": float(_expected_calibration_error(candidate_probs_arr, candidate_labels_arr, bins=10)),
    }
    return metrics


def predict_candidate_distribution(frame: pd.DataFrame, model: Pipeline, feature_columns: List[str]) -> np.ndarray:
    if frame.empty:
        return np.array([], dtype=np.float64)

    X = frame[feature_columns].to_numpy(dtype=np.float64)
    probabilities = model.predict_proba(X)[:, 1]
    return _normalize_probabilities(probabilities)


def heuristic_candidate_distribution(frame: pd.DataFrame, task: str) -> np.ndarray:
    if frame.empty:
        return np.array([], dtype=np.float64)

    task_key = task.strip().lower()

    if task_key == "goal":
        raw = (
            0.40 * frame["player_goals_per90"].to_numpy(dtype=np.float64)
            + 0.20 * frame["player_recent_goals_last5"].to_numpy(dtype=np.float64)
            + 0.15 * frame["player_goal_involvement_per90"].to_numpy(dtype=np.float64)
            + 0.10 * frame["team_attack_prior"].to_numpy(dtype=np.float64)
            + 0.10 * frame["position_attacker"].to_numpy(dtype=np.float64)
            + 0.05 * frame["team_trailing"].to_numpy(dtype=np.float64)
        )
    else:
        raw = (
            0.35 * frame["player_assists_per90"].to_numpy(dtype=np.float64)
            + 0.20 * frame["player_recent_assists_last5"].to_numpy(dtype=np.float64)
            + 0.20 * frame["player_goal_involvement_per90"].to_numpy(dtype=np.float64)
            + 0.15 * frame["team_attack_prior"].to_numpy(dtype=np.float64)
            + 0.10 * frame["position_midfielder"].to_numpy(dtype=np.float64)
        )

    raw = np.clip(raw, 1e-6, None)
    return _normalize_probabilities(raw)


def build_top_candidates(frame: pd.DataFrame, full_distribution: np.ndarray, top_k: int = 3) -> Tuple[List[Dict[str, object]], float]:
    if frame.empty or full_distribution.size == 0:
        return [], 0.0

    top_k = max(1, int(top_k))
    order = np.argsort(-full_distribution)
    top_indices = order[:top_k]
    top_mass = float(np.sum(full_distribution[top_indices]))

    if top_mass <= 0:
        renormalized = np.full(len(top_indices), 1.0 / max(1, len(top_indices)), dtype=np.float64)
    else:
        renormalized = full_distribution[top_indices] / top_mass

    payload = []
    for rank, (index, probability) in enumerate(zip(top_indices, renormalized), start=1):
        row = frame.iloc[int(index)]
        payload.append(
            {
                "rank": rank,
                "player_id": int(row["player_id"]),
                "player_name": str(row["player_name"]),
                "team_id": int(row["team_id"]),
                "team_name": str(row["team_name"]),
                "probability": float(probability),
                "full_distribution_probability": float(full_distribution[int(index)]),
            }
        )

    return payload, top_mass


def confidence_label_from_distribution(distribution: np.ndarray) -> Tuple[float, str]:
    if distribution.size == 0:
        return 0.0, "low"

    ordered = np.sort(distribution)[::-1]
    top1 = float(ordered[0])
    top2 = float(ordered[1]) if len(ordered) > 1 else 0.0
    margin = top1 - top2

    if top1 >= 0.45 and margin >= 0.15:
        return top1, "high"

    if top1 >= 0.30 and margin >= 0.08:
        return top1, "medium"

    return top1, "low"


def train_next_event_models(
    goal_frame: pd.DataFrame,
    assist_frame: pd.DataFrame,
    feature_columns: Optional[List[str]] = None,
    test_ratio: float = 0.2,
) -> Dict[str, object]:
    selected_features = feature_columns or FEATURE_COLUMNS

    artifact = {
        "version": "next_event_ranker_v1",
        "scope": "Top 5 leagues + UEFA Champions League",
        "trained_at_utc": datetime.datetime.utcnow().replace(microsecond=0).isoformat() + "Z",
        "feature_columns": selected_features,
        "tasks": {},
    }

    for task, frame in (("goal", goal_frame), ("assist", assist_frame)):
        if frame.empty:
            artifact["tasks"][task] = {
                "model": None,
                "train_metrics": evaluate_ranked_samples(frame, np.array([], dtype=np.float64)),
                "test_metrics": evaluate_ranked_samples(frame, np.array([], dtype=np.float64)),
                "train_samples": 0,
                "test_samples": 0,
                "note": "No training samples available for this task.",
            }
            continue

        train_frame, test_frame = split_samples_chronologically(frame, test_ratio=test_ratio)
        model = train_task_model(train_frame, selected_features)

        train_raw = model.predict_proba(train_frame[selected_features].to_numpy(dtype=np.float64))[:, 1]
        test_raw = model.predict_proba(test_frame[selected_features].to_numpy(dtype=np.float64))[:, 1] if not test_frame.empty else np.array([])

        train_metrics = evaluate_ranked_samples(train_frame, train_raw)
        test_metrics = evaluate_ranked_samples(test_frame, test_raw)

        artifact["tasks"][task] = {
            "model": model,
            "train_metrics": train_metrics,
            "test_metrics": test_metrics,
            "train_samples": int(train_frame["sample_id"].nunique()) if not train_frame.empty else 0,
            "test_samples": int(test_frame["sample_id"].nunique()) if not test_frame.empty else 0,
            "note": "Binary ranker with per-snapshot probability normalization.",
        }

    return artifact


def save_artifact(artifact: Dict[str, object], artifact_path: Path = DEFAULT_ARTIFACT_PATH) -> Path:
    artifact_path.parent.mkdir(parents=True, exist_ok=True)
    with artifact_path.open("wb") as file_obj:
        pickle.dump(artifact, file_obj)
    return artifact_path


def load_artifact(artifact_path: Path = DEFAULT_ARTIFACT_PATH) -> Optional[Dict[str, object]]:
    if not artifact_path.exists():
        return None

    with artifact_path.open("rb") as file_obj:
        return pickle.load(file_obj)


class NextEventInferenceService:
    def __init__(self, artifact_path: Path = DEFAULT_ARTIFACT_PATH):
        self.artifact_path = artifact_path
        self._artifact: Optional[Dict[str, object]] = None
        self._artifact_mtime: Optional[float] = None

    def _refresh_artifact(self) -> Optional[Dict[str, object]]:
        if not self.artifact_path.exists():
            self._artifact = None
            self._artifact_mtime = None
            return None

        mtime = self.artifact_path.stat().st_mtime
        if self._artifact is None or self._artifact_mtime != mtime:
            self._artifact = load_artifact(self.artifact_path)
            self._artifact_mtime = mtime

        return self._artifact

    def predict_for_match(self, db, match, minute_override: Optional[int] = None, top_k: int = 3) -> Dict[str, object]:
        builder = NextEventFeatureBuilder(db)
        candidates, context = builder.build_live_candidate_frame(match, minute_override=minute_override)

        if candidates.empty:
            return {
                "match_id": match.id,
                "scope": "Top 5 leagues + UEFA Champions League",
                "model_version": "heuristic_only",
                "generated_at_utc": datetime.datetime.utcnow().replace(microsecond=0).isoformat() + "Z",
                "global_limitations": [
                    "No on-pitch candidates could be inferred from available squad and event data.",
                ],
                "next_goal": {
                    "task": "goal",
                    "minute_context": int(context.get("minute", 1)),
                    "source": "unavailable",
                    "candidate_count": 0,
                    "top_candidates": [],
                    "top3_probability_mass_from_full_distribution": 0.0,
                    "confidence_score": 0.0,
                    "confidence_label": "low",
                    "data_limitations": ["Model cannot run without candidate players."],
                },
                "next_assist": {
                    "task": "assist",
                    "minute_context": int(context.get("minute", 1)),
                    "source": "unavailable",
                    "candidate_count": 0,
                    "top_candidates": [],
                    "top3_probability_mass_from_full_distribution": 0.0,
                    "confidence_score": 0.0,
                    "confidence_label": "low",
                    "data_limitations": ["Model cannot run without candidate players."],
                },
            }

        artifact = self._refresh_artifact()
        feature_columns = FEATURE_COLUMNS

        model_version = "heuristic_only"
        global_limitations = [
            "Predictions are baseline rankings conditioned on available timeline and roster data.",
            "Probabilities are normalized within inferred on-pitch candidates only.",
        ]

        if artifact:
            model_version = str(artifact.get("version", "next_event_ranker"))
            feature_columns = artifact.get("feature_columns", FEATURE_COLUMNS)
        else:
            global_limitations.append("No trained artifact found; using heuristic fallback scores.")

        task_payloads: Dict[str, Dict[str, object]] = {}

        for task in ("goal", "assist"):
            source = "heuristic_fallback"
            if artifact and artifact.get("tasks", {}).get(task, {}).get("model") is not None:
                model = artifact["tasks"][task]["model"]
                distribution = predict_candidate_distribution(candidates, model, feature_columns)
                source = "trained_model"
            else:
                distribution = heuristic_candidate_distribution(candidates, task)

            top_candidates, top_mass = build_top_candidates(candidates, distribution, top_k=top_k)
            confidence_score, confidence_label = confidence_label_from_distribution(distribution)

            task_limitations = []
            if context.get("missing_player_stats", 0) > 0:
                task_limitations.append(
                    "Some players lack season stats; ranking relies more on team priors and inferred lineups."
                )
            if task == "assist":
                task_limitations.append(
                    "Assist labels are sparse in historical feeds, so assist confidence may be lower than goal confidence."
                )
            if source != "trained_model":
                task_limitations.append("Heuristic fallback is active because no trained model artifact is available.")

            task_payloads[task] = {
                "task": task,
                "minute_context": int(context.get("minute", 1)),
                "source": source,
                "candidate_count": int(context.get("candidate_count", len(candidates))),
                "top_candidates": top_candidates,
                "top3_probability_mass_from_full_distribution": float(top_mass),
                "confidence_score": float(confidence_score),
                "confidence_label": confidence_label,
                "data_limitations": task_limitations,
            }

        return {
            "match_id": match.id,
            "scope": "Top 5 leagues + UEFA Champions League",
            "model_version": model_version,
            "generated_at_utc": datetime.datetime.utcnow().replace(microsecond=0).isoformat() + "Z",
            "global_limitations": global_limitations,
            "next_goal": task_payloads["goal"],
            "next_assist": task_payloads["assist"],
        }


next_event_inference_service = NextEventInferenceService()
