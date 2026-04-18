# Task: ML Model for Next Goal Scorer and Next Assist

## Goal
Predict the most likely next goal scorer and next assister during a match.

## Feasibility
Possible at basic level; high-quality predictions require richer event data than football-data alone.

## Data Requirements
- Live context: minute, scoreline, red cards, substitutions, on-pitch players.
- Historical player priors: goals per 90, assists per 90, shots per 90, role.
- Team context: attacking strength, possession trend, opponent defensive strength.

## Model Strategy
- Phase 1: Candidate ranking model (Top K scorers/assisters).
- Phase 2: Live update model every event window.
- Phase 3: Calibrated probabilities and confidence bands.

## Recommended Metrics
- Top-1 and Top-3 accuracy.
- Log loss and Brier score.
- Calibration error by match minute segment.

## Known Constraints
- With only scorers/cards/lineups, prediction quality will be moderate.
- For strong results, add event-rich source data.

## Acceptance Criteria
- For each live match, API returns Top 3 next-goal candidates.
- For each live match, API returns Top 3 next-assist candidates.
- Probabilities sum to 1 for each prediction type.
- Model performance dashboard is available for evaluation.

## Milestones
1. Build labeled dataset from historical events.
2. Train baseline ranking model.
3. Integrate live features and inference endpoint.
4. Add monitoring and retraining loop.
