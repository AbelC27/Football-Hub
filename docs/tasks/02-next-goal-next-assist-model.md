# Task: ML Baseline for Next Goal Scorer and Next Assist

## Scope
- Competition scope is restricted to Top 5 leagues + UEFA Champions League.
- Endpoint scope and training data scope must follow this filter.

## Baseline Architecture
- Training data is generated from historical goal events.
- Each goal event creates a candidate-ranking snapshot for on-pitch players.
- Two binary rankers are trained:
	- next goal scorer
	- next assist provider
- Candidate probabilities are normalized per snapshot and returned as Top 3.

## Feature Engineering (Baseline v1)
- Match state:
	- minute context
	- inferred scoreline from timeline events
	- leading/trailing status
- Lineup context:
	- inferred on-pitch players (probable XI + substitutions)
	- probable starter flag
- Discipline context:
	- team yellow/red card counts
	- player yellow/red card counts
- Player form and profile priors:
	- season goals, assists, rating, minutes
	- goals/assists in recent supported matches
	- per-90 involvement rates
- Team priors:
	- attacking and defensive rates from recent supported matches
	- standings-based fallback for points-per-match and goal-diff-per-match

## Training Workflow
Run from `backend`:

```powershell
python -m ai.train_next_event_ranker
```

Outputs:
- `backend/ai/artifacts/next_event_ranker.pkl`
- `backend/ai/artifacts/next_event_metrics.json`

## Evaluation Workflow
Run from `backend`:

```powershell
python -m ai.evaluate_next_event_ranker
```

Output:
- `backend/ai/artifacts/next_event_evaluation.json`

Reported metrics per task:
- Top-1 accuracy
- Top-3 accuracy
- Log loss
- Brier score
- ECE (10-bin expected calibration error)

## Inference Endpoint
- `GET /api/v1/match/{match_id}/next-events/prediction`
- Optional query: `minute` (1..130)

Response includes:
- Top 3 next-goal candidates with probabilities
- Top 3 next-assist candidates with probabilities
- confidence score and confidence label (`high`, `medium`, `low`)
- global and task-level data limitation notes

## Confidence Labels
- `high`: strong top-1 probability and margin vs. second candidate
- `medium`: moderate top-1 probability and separation
- `low`: weak separation and/or low top-1 probability

## Required Data Refresh Cadence
- Match events for in-play fixtures: every 1-2 minutes.
- Match status and scoreline snapshots: every 1 minute.
- Team standings and season priors: at least every 12 hours.
- Player season stats (minutes/goals/assists/rating): daily refresh minimum.
- Full model retraining:
	- weekly during active season
	- immediate retrain after schema/feature changes
	- immediate retrain when calibration or Top-3 metrics degrade beyond alert thresholds

## Operational Notes
- If no trained artifact is available, endpoint falls back to heuristic scoring and labels this explicitly.
- Assist prediction reliability is typically lower than goal prediction because assist labels are sparse in historical feeds.
- Returned probabilities are normalized over inferred on-pitch candidates, not the full registered squad.
