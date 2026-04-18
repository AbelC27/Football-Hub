# Task: Complete Match Page Experience

## Target Page
/match/[id]

## Goal
Deliver a full match hub with lineups, form, player drill-down, and AI insights.

## Required Sections
- Match header: score, status, kickoff time, venue.
- Lineups and substitutions.
- Match events: goals, assists, cards.
- Team form: last 5 matches for both teams.
- AI block: win/draw/loss probabilities, confidence, optional next-goal candidates.
- Full player list for both teams with clickable profile cards.

## Player Drill-Down
- Clicking a player opens detailed player page/card.
- Show photo, position, stats, and recent form.

## Performance Requirements
- Backend aggregates and caches match payload.
- Frontend polls or uses WebSocket for live state.
- Page should still render partial content if one data block fails.

## Acceptance Criteria
- All players are visible for both sides.
- Last 5 matches shown for both teams.
- AI prediction panel loads consistently.
- Each player card click leads to detailed player stats view.

## Milestones
1. Define page data contract.
2. Implement backend aggregator endpoint.
3. Implement UI sections with loading states.
4. Add live updates and resilience testing.
