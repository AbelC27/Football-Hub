"""
Train xG module with automatic granularity detection.

Outputs:
- ai/artifacts/xg_model.pkl
- ai/artifacts/xg_training_metrics.json
- ai/artifacts/xg_training_config.json
- ai/artifacts/xg_feature_docs.md
"""

import argparse
import json
from pathlib import Path
from typing import Any

try:
    from backend.database import SessionLocal
    from backend.ai.xg_model import (
        DEFAULT_XG_ARTIFACT_PATH,
        DEFAULT_XG_CONFIG_PATH,
        DEFAULT_XG_FEATURE_DOC_PATH,
        DEFAULT_XG_METRICS_PATH,
        XGTrainingConfig,
        build_metrics_view,
        save_xg_artifact,
        train_xg_artifact,
        write_feature_documentation,
    )
except ImportError:
    from database import SessionLocal
    from ai.xg_model import (
        DEFAULT_XG_ARTIFACT_PATH,
        DEFAULT_XG_CONFIG_PATH,
        DEFAULT_XG_FEATURE_DOC_PATH,
        DEFAULT_XG_METRICS_PATH,
        XGTrainingConfig,
        build_metrics_view,
        save_xg_artifact,
        train_xg_artifact,
        write_feature_documentation,
    )


def _serialize(obj: Any) -> Any:
    if isinstance(obj, dict):
        return {key: _serialize(value) for key, value in obj.items()}
    if isinstance(obj, list):
        return [_serialize(value) for value in obj]
    if hasattr(obj, "item"):
        return obj.item()
    return obj


def main() -> None:
    parser = argparse.ArgumentParser(description="Train pre-match and live xG module")
    parser.add_argument("--artifact", type=str, default=str(DEFAULT_XG_ARTIFACT_PATH))
    parser.add_argument("--metrics", type=str, default=str(DEFAULT_XG_METRICS_PATH))
    parser.add_argument("--config", type=str, default=str(DEFAULT_XG_CONFIG_PATH))
    parser.add_argument("--feature-doc", type=str, default=str(DEFAULT_XG_FEATURE_DOC_PATH))
    parser.add_argument("--seed", type=int, default=42)
    parser.add_argument("--test-ratio", type=float, default=0.2)
    parser.add_argument("--history-window", type=int, default=12)
    parser.add_argument("--min-training-rows", type=int, default=120)
    parser.add_argument("--shot-min-rows", type=int, default=300)
    parser.add_argument("--poisson-alpha", type=float, default=0.18)

    args = parser.parse_args()

    artifact_path = Path(args.artifact)
    metrics_path = Path(args.metrics)
    config_path = Path(args.config)
    feature_doc_path = Path(args.feature_doc)

    config = XGTrainingConfig(
        seed=args.seed,
        test_ratio=args.test_ratio,
        history_window=args.history_window,
        min_training_rows=args.min_training_rows,
        shot_min_rows=args.shot_min_rows,
        poisson_alpha=args.poisson_alpha,
    )

    db = SessionLocal()
    try:
        print("Training xG module...")
        artifact = train_xg_artifact(db=db, config=config)

        save_xg_artifact(artifact, artifact_path=artifact_path)
        print(f"Saved xG artifact: {artifact_path}")

        metrics_payload = build_metrics_view(artifact)
        metrics_path.parent.mkdir(parents=True, exist_ok=True)
        metrics_path.write_text(json.dumps(_serialize(metrics_payload), indent=2), encoding="utf-8")
        print(f"Saved xG metrics: {metrics_path}")

        config_payload = {
            "reproducible_config": config.to_dict(),
            "artifact_path": str(artifact_path),
            "metrics_path": str(metrics_path),
            "feature_doc_path": str(feature_doc_path),
        }
        config_path.parent.mkdir(parents=True, exist_ok=True)
        config_path.write_text(json.dumps(config_payload, indent=2), encoding="utf-8")
        print(f"Saved xG reproducible config: {config_path}")

        write_feature_documentation(artifact, destination=feature_doc_path)
        print(f"Saved xG feature docs: {feature_doc_path}")

        test_metrics = artifact.get("metrics", {}).get("test", {})
        print("\nTraining summary")
        print(f"- Mode: {artifact.get('mode', 'xg_proxy')}")
        print(f"- Training rows: {artifact.get('training_data', {}).get('rows', 0)}")
        print(f"- Test MAE: {test_metrics.get('mae', 0.0):.4f}")
        print(f"- Test RMSE: {test_metrics.get('rmse', 0.0):.4f}")
        print(f"- Test calibration MAE (10-bin): {test_metrics.get('calibration_mae_10_bin', 0.0):.4f}")
        print(f"- Test P(score>=1) ECE (10-bin): {test_metrics.get('prob_score_ge1_ece_10_bin', 0.0):.4f}")

    finally:
        db.close()


if __name__ == "__main__":
    main()
