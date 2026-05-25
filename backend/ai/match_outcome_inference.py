"""Inference singleton for the 1X2 match-outcome model.

Lazy-loads the PyTorch weights, the StandardScaler and the isotonic
calibrators on first use. Reloads them transparently when the underlying
files change on disk (training writes new artifacts -> next request
picks them up). Pattern mirrors `XGInferenceService` so the rest of the
backend stays consistent.

If LightGBM produced a clearly better test log-loss during training, we
still default to the calibrated PyTorch network for the deployed
endpoint - the thesis chapter 5 is built around the neural net. The
LightGBM model is kept in the artifact for the comparison study only.
"""

from __future__ import annotations

import json
import logging
import pickle
import threading
from pathlib import Path
from typing import Dict, List, Optional, Tuple

import numpy as np
import torch

try:
    from backend.ai.match_outcome_features import FEATURE_COLUMNS, build_inference_features
    from backend.ai.model import FootballPredictor
except ImportError:
    from ai.match_outcome_features import FEATURE_COLUMNS, build_inference_features  # type: ignore[no-redef]
    from ai.model import FootballPredictor  # type: ignore[no-redef]


logger = logging.getLogger(__name__)

ARTIFACT_DIR = Path(__file__).resolve().parent / "artifacts"
TORCH_WEIGHTS_PATH = Path(__file__).resolve().parent / "football_model.pth"
ARTIFACTS_PATH = ARTIFACT_DIR / "match_outcome_artifacts.pkl"


class MatchOutcomeInferenceService:
    """Loads the trained model on first call and caches it across requests."""

    def __init__(self) -> None:
        self._lock = threading.Lock()
        self._model: Optional[FootballPredictor] = None
        self._scaler = None
        self._calibrators = None
        self._temperature: float = 1.0
        self._weights_mtime: Optional[float] = None
        self._artifacts_mtime: Optional[float] = None

    def _refresh(self) -> bool:
        """Reload artifacts if the underlying files changed.

        Returns True when the service is ready, False when the artifacts
        are missing (caller should fall back to the heuristic).
        """
        if not TORCH_WEIGHTS_PATH.exists() or not ARTIFACTS_PATH.exists():
            return False

        weights_mtime = TORCH_WEIGHTS_PATH.stat().st_mtime
        artifacts_mtime = ARTIFACTS_PATH.stat().st_mtime

        with self._lock:
            if (
                self._model is not None
                and self._weights_mtime == weights_mtime
                and self._artifacts_mtime == artifacts_mtime
            ):
                return True

            with ARTIFACTS_PATH.open("rb") as fh:
                payload: Dict = pickle.load(fh)

            self._scaler = payload["scaler"]
            self._calibrators = payload["isotonic_calibrators"]
            self._temperature = float(payload.get("temperature", 1.0) or 1.0)
            input_size = len(payload.get("feature_columns", FEATURE_COLUMNS))

            model = FootballPredictor(
                input_size=input_size,
                hidden1=96,
                hidden2=48,
                hidden3=24,
                dropout=0.20,
            )
            state = torch.load(TORCH_WEIGHTS_PATH, map_location="cpu", weights_only=True)
            model.load_state_dict(state)
            model.eval()
            self._model = model
            self._weights_mtime = weights_mtime
            self._artifacts_mtime = artifacts_mtime

        logger.info("MatchOutcomeInferenceService reloaded artifacts (T=%.3f)", self._temperature)
        return True

    def is_ready(self) -> bool:
        return self._refresh()

    def predict(self, features: np.ndarray) -> Optional[Tuple[float, float, float]]:
        if features is None:
            return None
        if not self._refresh():
            return None
        with self._lock:
            scaled = self._scaler.transform(features.astype(np.float32))
            with torch.no_grad():
                logits = self._model(torch.from_numpy(scaled).float()).numpy()[0]

            # Temperature scaling: divide logits by T before softmax.
            t = max(self._temperature, 1e-3)
            shifted = logits / t
            shifted -= shifted.max()
            exp = np.exp(shifted)
            probs = exp / exp.sum()

        import os as _os

        if _os.getenv("TERRABALL_ENABLE_ISOTONIC", "").strip() == "1":
            calibrated = np.empty_like(probs)
            for cls in range(3):
                calibrated[cls] = self._calibrators[cls].predict([probs[cls]])[0]
            calibrated = np.clip(calibrated, 1e-6, 1.0)
            calibrated = calibrated / calibrated.sum()
            probs = calibrated

        return float(probs[0]), float(probs[1]), float(probs[2])


match_outcome_inference_service = MatchOutcomeInferenceService()


def predict_for_match(db, match) -> Optional[Tuple[float, float, float]]:
    """Convenience wrapper used by the prediction generator."""
    features = build_inference_features(db, match)
    if features is None:
        return None
    return match_outcome_inference_service.predict(features)


