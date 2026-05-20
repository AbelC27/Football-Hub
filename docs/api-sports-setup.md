# api-sports.io integration

This guide covers wiring api-sports.io (api-football v3) into Football-Hub for
Premier League goals/assists/events without disturbing the existing
football-data.org pipeline. All cross-provider IDs live in the
`provider_id_map` junction table (no existing tables are altered).

## 1. Get a key

1. Sign up at [api-sports.io](https://www.api-sports.io/) for a free key
   (100 calls/day).
2. Add the key to `backend/.env`:
   ```
   API_FOOTBALL_KEY=your_key_here
   ```
3. Restart the FastAPI server so the new env var is picked up.

## 2. Apply the migration

The migration creates `provider_id_map` and adds three columns to
`match_events`. It is idempotent and safe to re-run.

1. Open the Supabase project's **SQL Editor**.
2. Paste the full contents of
   `backend/scripts/migrations/2026_05_apisports_integration.sql`.
3. Run it. The script wraps everything in a transaction and uses
   `IF NOT EXISTS`, so a partial previous run won't break it.

## 3. Build the ID mappings (one-time, ~21 calls)

This is a one-shot pass that:

- maps the Premier League itself (local id `2021` ↔ external id `39`),
- fuzzy-matches your local PL teams to api-sports teams,
- fetches each mapped team's squad and fuzzy-matches players.

```bash
cd backend
.venv/bin/python scripts/map_pl_apisports.py
```

Useful flags:

| Flag | Default | What it does |
| ---- | ------- | ------------ |
| `--season YYYY` | current PL season | Override the season year (e.g. `2024` for 2024/25). |
| `--threshold INT` | `85` | Minimum fuzzy score (0–100) to accept a match. |
| `--refresh` | off | Overwrite existing mappings instead of skipping them. |

If `rapidfuzz` is installed it's used automatically; otherwise the script
falls back to `difflib.SequenceMatcher` (no extra installs needed).

The script prints a per-team table (matched/unmatched + score) and a final
summary including the number of api-sports calls used. Expect roughly **21
calls** total: 1 for the team list + 20 for squads.

## 4. Sync player season stats (run on a cron, 2 calls)

Updates `players.goals_season`, `assists_season`, `rating_season`, and
`minutes_played` from api-sports's `topscorers` and `topassists` endpoints.

```bash
cd backend
.venv/bin/python scripts/sync_pl_player_stats.py
```

Flags: `--season YYYY` (defaults to current).

Suggested cron entry — refresh once a day at 04:00 UTC:

```cron
0 4 * * * cd /path/to/Football-Hub/backend && .venv/bin/python scripts/sync_pl_player_stats.py >> /var/log/fh-sync-stats.log 2>&1
```

## 5. Lazy match events

The `/api/v1/match/{match_id}/events` endpoint:

- returns locally-cached events immediately if any are stored,
- otherwise (Premier League finished matches only) resolves the api-sports
  fixture id and fetches its events,
- maps each api-sports team/player back to local IDs through
  `provider_id_map`,
- persists the new `MatchEvent` rows so subsequent requests skip the network.

Worst case it costs **2 api calls per match** (one date lookup + one events
call). Cached after the first hit.

## 6. Quota notes

- The free tier is **100 calls / day**, reset at UTC midnight.
- The local client (`backend/services/apisports.py`) tracks calls in a
  process counter and refuses new calls at 95 to leave headroom.
- If the upstream provider returns `429` or the local guard trips, the
  endpoint responds with `503 {"detail": "Provider quota exceeded; try later."}`
  until the next UTC midnight.
- The counter is per-process. If you run multiple workers, treat the
  guard as a soft signal, not a strict global limit.

## 7. What this integration does *not* touch

- `backend/services/data_ingestion.py` (the pre-existing api-sports calls
  used by the seeders) is left as-is.
- `backend/services/football_data_org.py`, `backend/scheduler.py`, and the
  frontend are unchanged.
- The new sync script is **manual / cron**: it is intentionally not wired
  into the scheduler.
