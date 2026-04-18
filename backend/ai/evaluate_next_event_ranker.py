"""
Evaluate trained next-goal / next-assist baseline models.

Metrics reported per task:
- Top-1 accuracy
- Top-3 accuracy
- Log loss
- Brier score
- ECE (10-bin calibration error)
"""

import argparse
import datetime
import json
from pathlib import Path

try:
    from backend.database import SessionLocal
    from backend.ai.next_event_features import FEATURE_COLUMNS, NextEventFeatureBuilder
    from backend.ai.next_event_ranker import (
        DEFAULT_ARTIFACT_PATH,
        evaluate_ranked_samples,
        load_artifact,
        split_samples_chronologically,
    )
except ImportError:
    from database import SessionLocal
    from ai.next_event_features import FEATURE_COLUMNS, NextEventFeatureBuilder
    from ai.next_event_ranker import (
        DEFAULT_ARTIFACT_PATH,
        evaluate_ranked_samples,
        load_artifact,
        split_samples_chronologically,
    )


def _to_serializable(obj):
    if isinstance(obj, dict):
        return {key: _to_serializable(value) for key, value in obj.items()}
    if isinstance(obj, list):
        return [_to_serializable(value) for value in obj]
    if hasattr(obj, "item"):
        return obj.item()
    return obj


def evaluate_task(task: str, frame, model, feature_columns):
    if frame.empty:
        return {
            "samples": 0,
            "top1": 0.0,
            "top3": 0.0,
            "log_loss": 0.0,
            "brier": 0.0,
            "ece_10_bin": 0.0,
            "note": "No evaluation samples for this task.",
        }

    if model is None:
        return {
            "samples": int(frame["sample_id"].nunique()),
            "top1": 0.0,
            "top3": 0.0,
            "log_loss": 0.0,
            "brier": 0.0,
            "ece_10_bin": 0.0,
            "note": "No trained model available for this task.",
        }

    raw_scores = model.predict_proba(frame[feature_columns].to_numpy(dtype=float))[:, 1]
    metrics = evaluate_ranked_samples(frame, raw_scores)
    metrics["note"] = "Evaluation on chronological holdout samples."
    return metrics


def main():
    parser = argparse.ArgumentParser(description="Evaluate next-event ranking models")
    parser.add_argument("--artifact", type=str, default=str(DEFAULT_ARTIFACT_PATH))
    parser.add_argument("--output", type=str, default="ai/artifacts/next_event_evaluation.json")
    parser.add_argument("--test-ratio", type=float, default=0.2)
    args = parser.parse_args()

    artifact_path = Path(args.artifact)
    output_path = Path(args.output)

    artifact = load_artifact(artifact_path)
    if not artifact:
        raise RuntimeError(
            f"Artifact not found at {artifact_path}. Train first with ai/train_next_event_ranker.py"
        )

    feature_columns = artifact.get("feature_columns", FEATURE_COLUMNS)

    db = SessionLocal()
    try:
        builder = NextEventFeatureBuilder(db)

        goal_frame = builder.build_training_frame("goal")
        assist_frame = builder.build_training_frame("assist")

        _, goal_test = split_samples_chronologically(goal_frame, test_ratio=args.test_ratio)
        _, assist_test = split_samples_chronologically(assist_frame, test_ratio=args.test_ratio)

        goal_model = artifact.get("tasks", {}).get("goal", {}).get("model")
        assist_model = artifact.get("tasks", {}).get("assist", {}).get("model")

        result = {
            "artifact": str(artifact_path),
            "model_version": artifact.get("version", "unknown"),
            "evaluated_at_utc": datetime.datetime.utcnow().replace(microsecond=0).isoformat() + "Z",
            "scope": artifact.get("scope", "Top 5 leagues + UEFA Champions League"),
            "tasks": {
                "goal": evaluate_task("goal", goal_test, goal_model, feature_columns),
                "assist": evaluate_task("assist", assist_test, assist_model, feature_columns),
            },
        }

        output_path.parent.mkdir(parents=True, exist_ok=True)
        output_path.write_text(json.dumps(_to_serializable(result), indent=2), encoding="utf-8")

        print(f"Saved evaluation to {output_path}")
        for task, metrics in result["tasks"].items():
            print(
                f"- {task}: samples={metrics.get('samples', 0)} "
                f"Top1={metrics.get('top1', 0.0):.3f} "
                f"Top3={metrics.get('top3', 0.0):.3f} "
                f"LogLoss={metrics.get('log_loss', 0.0):.3f} "
                f"ECE={metrics.get('ece_10_bin', 0.0):.3f}"
            )

    finally:
        db.close()


if __name__ == "__main__":
    main()
