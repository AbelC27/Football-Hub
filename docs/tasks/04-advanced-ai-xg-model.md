# Task: Advanced AI - Expected Goals (xG)

## Goal
Add xG predictions per team and optionally per player.

## Feasibility
Possible only if you have shot-level features. Without shot-level data, build an xG-proxy model and label it clearly.

## True xG Needs
- Shot location.
- Shot type and body part.
- Assist type.
- Pressure/defender context if available.

## If Data Is Limited
- Build xG-proxy from available match and player aggregates.
- Use clear naming to avoid confusion with true event xG.

## Product Outputs
- Pre-match team xG forecast.
- Live updated xG trend by minute segment.
- Optional player expected scoring contribution.

## Acceptance Criteria
- xG value shown for both teams on match page.
- Historical xG chart is available by match timeline.
- Model evaluation uses MAE and calibration checks.

## Milestones
1. Confirm data granularity.
2. Build feature pipeline.
3. Train and validate xG model.
4. Expose endpoint and add chart UI.
