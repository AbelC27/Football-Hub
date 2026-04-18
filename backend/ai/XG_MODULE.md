# xG Module (True vs Proxy)

## Purpose
This module provides two modes:

- `true_xg`: used only when shot-level rows with coordinates and goal outcomes are available.
- `xg_proxy`: fallback mode using aggregate match statistics and team history.

Current project data granularity usually leads to `xg_proxy`, and API responses expose this explicitly.

## Scope
Top 5 leagues + UEFA Champions League.

## Training (Reproducible)
Run from backend directory:

```bash
python -m ai.train_xg_model \
  --seed 42 \
  --test-ratio 0.2 \
  --history-window 12 \
  --min-training-rows 120 \
  --shot-min-rows 300 \
  --poisson-alpha 0.18
```

Outputs:

- `backend/ai/artifacts/xg_model.pkl`
- `backend/ai/artifacts/xg_training_metrics.json`
- `backend/ai/artifacts/xg_training_config.json`
- `backend/ai/artifacts/xg_feature_docs.md`

## Evaluation + Calibration
Training output includes:

- `mae`
- `rmse`
- `r2`
- `calibration_mae_10_bin`
- `prob_score_ge1_ece_10_bin`
- calibration bins for train/test

## Inference
The inference service auto-loads the latest artifact:

- pre-match forecast (team xG baseline)
- live xG trend by minute (with explicit proxy disclaimers when applicable)

## Honest Labeling
If shot-level schema is absent or insufficient, the module automatically:

- switches to `xg_proxy`
- includes explicit granularity reasons in API payload
- emits UI-safe disclaimers via API response fields
