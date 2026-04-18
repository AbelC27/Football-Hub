# TerraBall

TerraBall is a full-stack football analytics platform built for a bachelor capstone project.

It combines:

- live and scheduled match data
- standings, team and player exploration
- match experience pages with events, form, and lineups
- AI predictions (match outcome, next event ranking, xG pre-match/live)
- fantasy features (legacy team mode and player-based mode)

Scope is focused on Top 5 European leagues plus UEFA Champions League.

## Tech Stack

- Frontend: Next.js 16, React 19, TypeScript, Tailwind CSS 4
- Backend: FastAPI, SQLAlchemy, APScheduler
- Database: PostgreSQL 15 (Docker)
- AI/ML: PyTorch, scikit-learn
- Data providers: football-data.org, API-Football, TheSportsDB

## Repository Structure

```text
.
|-- backend/
|   |-- main.py
|   |-- models.py
|   |-- schemas.py
|   |-- scheduler.py
|   |-- routers/
|   |-- services/
|   `-- ai/
|-- frontend/
|   |-- src/app/
|   |-- src/components/
|   `-- package.json
|-- docs/tasks/
|-- docker-compose.yml
`-- Readme.md
```

## Prerequisites

- Python 3.10+
- Node.js 18+
- Docker Desktop

## Quick Start

### 1. Start PostgreSQL

From project root:

```bash
docker-compose up -d
```

### 2. Backend Setup

From `backend/`:

```bash
python -m venv venv
venv\Scripts\activate
pip install -r requirements.txt
```

If auth dependencies are missing in your local environment, install:

```bash
pip install "python-jose[cryptography]" "passlib[argon2]"
```

Initialize schema:

```bash
python migrate.py
```

Run API server:

```bash
uvicorn main:app --reload
```

Backend URL:

- http://localhost:8000
- Swagger: http://localhost:8000/docs

### 3. Frontend Setup

From `frontend/`:

```bash
npm install
npm run dev
```

Frontend URL:

- http://localhost:3000

## Environment Variables

Create `backend/.env` (optional but recommended):

```env
DATABASE_URL=postgresql://user:password@localhost/football_analytics
FOOTBALL_DATA_ORG_KEY=your_key_here
API_FOOTBALL_KEY=your_key_here
THESPORTSDB_KEY=3
FOOTBALL_DATA_COMPETITIONS=PL,PD,BL1,SA,FL1
```

Notes:

- `FOOTBALL_DATA_ORG_KEY` is important for scheduler sync and reliable data refresh.
- `THESPORTSDB_KEY=3` is the public test key.
- Current frontend API calls are hardcoded to `http://localhost:8000`, so run backend on that host/port in local development.

## Data Ingestion and Refresh

### Automatic Refresh (recommended)

On backend startup, APScheduler:

- syncs fixtures/teams/leagues for configured competitions every 60 seconds
- generates predictions every hour

### Manual Scripts

From `backend/`:

```bash
python seed_events.py
```

Seeds recent events and match statistics.

```bash
python seed_football_data_org.py
```

Destructive full reseed (drops and recreates tables).

```bash
python migrate_fantasy_player_mode.py
```

Additive migration for player-based fantasy tables.

## AI Modules

### xG Module

The xG module auto-selects mode:

- `true_xg` when shot-level data is sufficient
- `xg_proxy` otherwise (with explicit disclaimers in API payload)

Train from `backend/`:

```bash
python -m ai.train_xg_model --seed 42 --test-ratio 0.2 --history-window 12 --min-training-rows 120 --shot-min-rows 300 --poisson-alpha 0.18
```

Artifacts are written to `backend/ai/artifacts/`.

### Next Event Ranking

Match endpoint for next-goal and next-assist Top-3 candidates:

- `GET /api/v1/match/{match_id}/next-events/prediction`

## API Overview

### Core (`/api/v1`)

- `GET /leagues`
- `GET /live-matches`
- `GET /match/{match_id}/details`
- `GET /match/{match_id}/experience`
- `GET /match/{match_id}/prediction`
- `GET /match/{match_id}/next-events/prediction`
- `GET /match/{match_id}/xg/pre-match`
- `GET /match/{match_id}/xg/live`
- `GET /match/{match_id}/events`
- `GET /match/{match_id}/statistics`
- `GET /league/{league_id}/standings`
- `GET /teams`
- `GET /teams/{team_id}`
- `GET /teams/{team_id}/statistics`
- `GET /teams/{team1_id}/vs/{team2_id}`
- `GET /players`
- `GET /players/{player_id}`
- `GET /players/{player_id}/enhanced`
- `GET /players/{player1_id}/vs/{player2_id}`

### Auth (`/api/v1/auth`)

- `POST /register`
- `POST /login`
- `GET /me`

### Search (`/api/v1/search`)

- `GET /teams`
- `GET /players`
- `GET /all`

### Fantasy (`/api/v1/fantasy`)

Legacy team mode:

- `GET /my-teams`
- `POST /select-teams`
- `GET /my-points`
- `GET /leaderboard`

Player mode:

- `GET /player-mode/rules`
- `GET /player-mode/players`
- `GET /player-mode/squad`
- `POST /player-mode/squad`
- `GET /player-mode/matchday/{matchday_key}/picks`
- `PUT /player-mode/matchday/{matchday_key}/picks`
- `POST /player-mode/matchday/{matchday_key}/transfers`
- `GET /player-mode/matchday/{matchday_key}/points`
- `GET /player-mode/leaderboard`

### WebSocket

- `WS /ws/live`

## Frontend Routes

- `/` live dashboard
- `/match/[id]` match experience
- `/league/[id]` league detail
- `/team/[id]` team detail
- `/team/[id]/statistics` team stats
- `/player/[id]` player detail
- `/compare/players/[id1]/vs/[id2]` player comparison
- `/compare/teams/[id1]/vs/[id2]` team comparison
- `/fantasy` fantasy hub
- `/profile` profile and favorites
- `/search` search page
- `/teams` team listing
- `/login` and `/register`

## Testing

Frontend (from `frontend/`):

```bash
npm test
```

Backend currently uses script-based tests/checks in `backend/` (examples):

```bash
python test_match_experience_contract.py
python test_next_event_prediction_contract.py
python test_prediction.py
```

## Troubleshooting

- Import errors when starting backend: run commands from `backend/` and ensure virtual environment is active.
- No fresh matches: verify `FOOTBALL_DATA_ORG_KEY` and watch backend logs for scheduler sync results.
- Frontend cannot reach API: ensure backend is running at `http://localhost:8000`.
- PostgreSQL issues: confirm container is up (`docker ps`) and `DATABASE_URL` is valid.

## Production Notes

- Replace wildcard CORS in backend with your frontend origin(s).
- Use a real JWT secret and do not keep defaults.
- Move provider keys to secure secret management.
- Add reverse proxy/TLS and environment-specific configs.