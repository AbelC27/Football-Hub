# Task: Deep Fantasy - Player-Based System with Salary Cap

## Goal
Move from team picks to player picks with budget and scoring rules.

## Core Mechanics
- User budget (salary cap).
- Player prices updated by form and minutes.
- Position constraints (GK, DEF, MID, FWD).
- Matchday lock and transfer rules.

## Scoring Rules (Example)
- Goals, assists, clean sheet, saves, key passes.
- Penalties for yellow/red cards and own goals.
- Captain multiplier.

## Data Requirements
- Reliable lineups and minutes.
- Player event data (goals, assists, cards).
- Team and fixture difficulty context.

## Acceptance Criteria
- User can create valid squad under budget.
- Matchday points are computed correctly.
- Leaderboard updates after match completion.
- Transfers and captain changes follow rules.

## Milestones
1. Define fantasy schema and rules.
2. Build pricing engine.
3. Build squad builder UI and validations.
4. Build scoring processor and leaderboard.
