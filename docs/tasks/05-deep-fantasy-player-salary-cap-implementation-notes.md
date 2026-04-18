# Deep Fantasy Player Mode - Implementation Notes

## What Was Implemented
- Added a new player-based fantasy mode with salary cap and preserved legacy team-based mode.
- New backend schema supports squads, budget tracking, matchday picks, captain/vice-captain, transfers, points history, and matchday summaries.
- Added backend rules engine for:
  - squad validation (size, positions, team quotas)
  - budget validation
  - matchday deadline lock
  - transfer validation and transfer penalties
  - scoring and captain multiplier
- Added frontend Fantasy Manager flow using TanStack Query + React Hook Form + Zod + Sonner:
  - squad builder
  - matchday picks
  - transfers
  - matchday points
  - leaderboard
  - legacy mode tab for existing team-pick flow
- Scope is enforced to Top 5 leagues plus UCL in player-mode pool and processing.

## Migration Notes
1. Ensure backend dependencies are installed:
   - `cd backend`
   - `venv\Scripts\python -m pip install -r requirements.txt`
2. Apply additive fantasy migration:
   - `venv\Scripts\python migrate_fantasy_player_mode.py`
3. Restart backend server.
4. Ensure frontend dependencies are installed:
   - `cd frontend`
   - `npm install`
5. Open `/fantasy` in the UI and use the player-mode tabs.

### New Tables Created
- `fantasy_player_squads`
- `fantasy_squad_players`
- `fantasy_matchday_picks`
- `fantasy_transfers`
- `fantasy_points_history`
- `fantasy_matchday_summaries`

## Rollback Safety Notes
- Migration is additive and non-destructive for existing fantasy data.
- Legacy endpoints and logic remain available:
  - `/api/v1/fantasy/my-teams`
  - `/api/v1/fantasy/select-teams`
  - `/api/v1/fantasy/my-points`
  - `/api/v1/fantasy/leaderboard`
- Frontend includes a Legacy Team Mode tab, so existing user flow remains accessible.

### Safe Rollback Strategy
1. Keep code deployed but switch users to Legacy Team Mode if needed.
2. If hard rollback is required, deploy previous backend/frontend commit.
3. Optional DB cleanup (manual, only after rollback confirmation): drop the six new fantasy player-mode tables.

## Test Coverage Summary
- Per current instruction, automated test execution was intentionally skipped.
- Validation is expected through manual UI checks on:
  - squad creation under salary cap
  - matchday picks and deadline lock behavior
  - transfer constraints and penalty logic
  - matchday points rendering and leaderboard updates
