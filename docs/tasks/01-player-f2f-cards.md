# Task: Player F2F Card Comparison

## Goal
Create a head-to-head player comparison view with card-style visuals inspired by football games.

## Feasibility
Possible, but card attributes should be custom app ratings, not official EA/FIFA attributes.

## Data Needed
- Identity: name, team, position, nationality, age, photo.
- Performance: goals, assists, minutes, cards, recent form.
- Optional advanced: xG, xA, key passes, shots, progressive actions.

## Data Source Notes
- football-data paid plan helps with squads, lineups, scorers, cards.
- You still need a source for richer player stats and high-quality photos.

## Product Requirements
- Compare two players side by side.
- Show season totals and last 5 match trend.
- Show role-specific metrics (attacker, midfielder, defender, keeper).
- Add a single overall score computed by your own formula.

## Acceptance Criteria
- User can pick any two players from supported competitions.
- Cards render with photo, position, team, and key metrics.
- Comparison includes at least 8 meaningful stats.
- Mobile layout remains readable.

## Milestones
1. Define metric schema by position.
2. Build data aggregation endpoint.
3. Build F2F UI cards and comparison radar/bar charts.
4. Add caching and fallback behavior.
