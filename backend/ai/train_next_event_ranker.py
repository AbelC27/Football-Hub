"""
Train baseline ranking models for:
- next goal scorer
- next assist provider

Outputs:
- ai/artifacts/next_event_ranker.pkl
- ai/artifacts/next_event_metrics.json
"""

import argparse
import json
from pathlib import Path

try:
    from backend.database import SessionLocal
    from backend.ai.next_event_features import FEATURE_COLUMNS, NextEventFeatureBuilder
    from backend.ai.next_event_ranker import (
        DEFAULT_ARTIFACT_PATH,
        DEFAULT_METRICS_PATH,
        save_artifact,
        train_next_event_models,
    )
except ImportError:
    from database import SessionLocal
    from ai.next_event_features import FEATURE_COLUMNS, NextEventFeatureBuilder
    from ai.next_event_ranker import (
        DEFAULT_ARTIFACT_PATH,
        DEFAULT_METRICS_PATH,
        save_artifact,
        train_next_event_models,
    )


def _to_serializable(obj):
    if isinstance(obj, dict):
        return {key: _to_serializable(value) for key, value in obj.items()}
    if isinstance(obj, list):
        return [_to_serializable(value) for value in obj]
    if hasattr(obj, "item"):
        return obj.item()
    return obj


def _metrics_view(artifact):
    tasks = artifact.get("tasks", {})
    return {
        "version": artifact.get("version"),
        "scope": artifact.get("scope"),
        "trained_at_utc": artifact.get("trained_at_utc"),
        "feature_count": len(artifact.get("feature_columns", [])),
        "tasks": {
            task: {
                "train_samples": payload.get("train_samples", 0),
                "test_samples": payload.get("test_samples", 0),
                "train_metrics": payload.get("train_metrics", {}),
                "test_metrics": payload.get("test_metrics", {}),
                "note": payload.get("note", ""),
            }
            for task, payload in tasks.items()
        },
    }


def main():
    parser = argparse.ArgumentParser(description="Train next-goal and next-assist baseline rankers")
    parser.add_argument("--artifact", type=str, default=str(DEFAULT_ARTIFACT_PATH))
    parser.add_argument("--metrics", type=str, default=str(DEFAULT_METRICS_PATH))
    parser.add_argument("--test-ratio", type=float, default=0.2)
    args = parser.parse_args()

    artifact_path = Path(args.artifact)
    metrics_path = Path(args.metrics)

    db = SessionLocal()
    try:
        builder = NextEventFeatureBuilder(db)

        print("Building goal training frame...")
        goal_frame = builder.build_training_frame("goal")
        print(f"Goal training rows: {len(goal_frame)}")

        print("Building assist training frame...")
        assist_frame = builder.build_training_frame("assist")
        print(f"Assist training rows: {len(assist_frame)}")

        if goal_frame.empty and assist_frame.empty:
            raise RuntimeError(
                "No training samples available. Ensure match events and player/team data are seeded for Top 5 + UCL."
            )

        artifact = train_next_event_models(
            goal_frame=goal_frame,
            assist_frame=assist_frame,
            feature_columns=FEATURE_COLUMNS,
            test_ratio=args.test_ratio,
        )

        save_artifact(artifact, artifact_path)
        print(f"Saved artifact to {artifact_path}")

        metrics_payload = _metrics_view(artifact)
        metrics_path.parent.mkdir(parents=True, exist_ok=True)
        metrics_path.write_text(json.dumps(_to_serializable(metrics_payload), indent=2), encoding="utf-8")
        print(f"Saved metrics to {metrics_path}")

        print("\nTraining summary:")
        for task, payload in metrics_payload.get("tasks", {}).items():
            test_metrics = payload.get("test_metrics", {})
            print(
                f"- {task}: samples(train/test)={payload.get('train_samples', 0)}/{payload.get('test_samples', 0)} "
                f"Top1={test_metrics.get('top1', 0.0):.3f} "
                f"Top3={test_metrics.get('top3', 0.0):.3f} "
                f"LogLoss={test_metrics.get('log_loss', 0.0):.3f} "
                f"ECE={test_metrics.get('ece_10_bin', 0.0):.3f}"
            )

    finally:
        db.close()


if __name__ == "__main__":
    main()
