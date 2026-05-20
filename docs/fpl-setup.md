# Fantasy Premier League (FPL) integration

This guide covers wiring the public Fantasy Premier League JSON API into
Football-Hub as a *fallback / supplemental* provider for Premier League
events and per-player season stats. It supplements (does not replace) the
existing api-sports.io integration. All cross-provider IDs live in the
`provider_id_map` junction table — api-sports rows use `provider='apisports'`
and FPL rows use `provider='fpl'`, so the two coexist cleanly.

## 1. No key needed

FPL serves these endpoints to its own consumer site without a key. Just
make sure your machine can reach `https://fantasy.premierleague.com/api/`
outbound. The local client (`backend/services/fpl.py`) sends a polite
`User-Agent` header and enforces a minimum 0.4s spacing between calls. No
`.env` changes are required.

## 2. Build the ID mappings (one-time, **1 call**)

This pass:

- pins the league mapping (local `2021` ↔ external `1` — see note below),
- fuzzy-matches the 20 PL teams (using both `name` and `short_name`),
- fuzzy-matches every FPL `element` to a local `Player` scoped to its team.

```bash
cd backend
.venv/bin/python scripts/map_pl_fpl.py
```

Useful flags:

| Flag | Default | What it does |
| ---- | ------- | ------------ |
| `--threshold INT` | `85` | Minimum fuzzy score (0–100) to accept a match. Drop to `75` if some teams come back as UNMATCHED. |
| `--refresh` | off | Overwrite existing FPL mappings instead of skipping them. |
| `--players-only` | off | Skip the team pass (use existing FPL team mappings). |
| `--teams-only` | off | Skip the player pass. |

If `rapidfuzz` is installed it's used automatically; otherwise the script
falls back to `difflib.SequenceMatcher`.

> Note on the FPL "league id": the FPL API does not surface a competition
> id anywhere in `bootstrap-static`. The script persists `1` as the
> external id for the league mapping (the API is implicitly scoped to the
> Premier League). This is intentional and documented in
> `services/fpl.py` as `PL_FPL_LEAGUE_ID`.

> Common FPL `short_name` quirks the fuzzy matcher already handles:
> "Spurs" (Tottenham), "Man Utd", "Man City", "Newcastle", "Wolves",
> "Forest" (Nottingham Forest). If something still comes back as
> UNMATCHED, lower `--threshold` to 75 and re-run.

Total network calls: **1** (a single `bootstrap-static` fetch).

## 3. Daily player stats sync (**1 call**)

Updates `players.goals_season`, `assists_season`, `minutes_played`, plus
the FPL signal columns used for the overall rating
(`fpl_total_points`, `fpl_points_per_game`, `fpl_form`, `fpl_ict_index`,
`fpl_influence`, `fpl_creativity`, `fpl_threat`, `fpl_element_type`).
`players.rating_season` is left alone — FPL does not surface a rating
on a 0–10 scale, and we don't want to clobber any value api-sports may
have populated.

> **First run:** apply the FPL signal-fields migration once before
> running this script. Paste the contents of
> `backend/scripts/migrations/2026_05_fpl_player_signals.sql` into the
> Supabase SQL editor and run it. The migration is idempotent and only
> adds nullable columns to `players`.

```bash
cd backend
.venv/bin/python scripts/sync_pl_fpl_player_stats.py
```

Flags: `--mark-confidence-floor INT` (default `0`) — only update players
whose mapping confidence is `>=` floor.

Suggested cron entry — refresh once a day at 04:15 UTC, 15 minutes after
the api-sports sync so the two providers don't pile on simultaneously:

```cron
15 4 * * * cd /path/to/Football-Hub/backend && .venv/bin/python scripts/sync_pl_fpl_player_stats.py >> /var/log/fh-fpl-stats.log 2>&1
```

Total network calls: **1**.

## 4. Weekly events sync (**1 call**)

Backfills `MatchEvent` rows for finished PL fixtures. Resolves each FPL
fixture either via an existing `ProviderIdMap(provider='fpl', entity_type='match')`
row or by matching home/away team mappings + a kickoff-time tolerance
window (default ±6 hours).

```bash
cd backend
.venv/bin/python scripts/sync_pl_fpl_match_events.py --all-finished
```

Useful flags:

| Flag | Default | What it does |
| ---- | ------- | ------------ |
| `--all-finished` | on | Walk every finished fixture in the season. |
| `--event INT` | — | Process a single gameweek instead. |
| `--limit INT` | `50` | Cap fixtures actually written this run. |
| `--refresh` | off | Delete pre-existing FPL-origin event rows for a match before re-inserting. |
| `--match-window-hours INT` | `6` | Tolerance for matching kickoff to local `Match.start_time`. |

Suggested cron entry — Mondays 05:00 UTC, after the weekend's matches
have all finalized:

```cron
0 5 * * 1 cd /path/to/Football-Hub/backend && .venv/bin/python scripts/sync_pl_fpl_match_events.py --all-finished >> /var/log/fh-fpl-events.log 2>&1
```

Total network calls: **1**.

## 5. Lazy fallback in `/match/{id}/events`

The endpoint is now a graceful chain:

1. **Cache** — return locally-cached `MatchEvent` rows if any exist.
2. **Pre-checks** — non-PL matches and unfinished matches return `[]`.
3. **api-sports** — try the existing api-sports flow. If it persists at
   least one row, those are returned.
4. **FPL fallback** — if api-sports returned 0 rows, hit a network error,
   was missing a mapping, *or* raised `ApisportsQuotaExceeded`, the route
   then calls `services.fpl.persist_fpl_events_for_match(db, match)`. The
   shared helper resolves the FPL fixture id (`ProviderIdMap` lookup, or
   team-mapping + kickoff window) and writes events using the same row
   shape as the offline script.
5. **Empty** — if both providers come back empty, return `[]`.

`503 Provider quota exceeded` is **only** returned when api-sports raised
quota *and* the FPL fallback also failed (or returned zero rows).

## 6. Notes / caveats

- **No minute-by-minute timing.** FPL fixture stats are aggregated counts
  per player per fixture, so `MatchEvent.minute` is always `None` for
  FPL-origin rows. The `MatchEvent.minute` column is a plain `Integer` (no
  `nullable=False`), so this works without any migration changes.

- **Assists are separate events.** FPL does not pair a scorer with an
  assister — there is no way to know which goal each assist belongs to.
  We therefore emit `MatchEvent(event_type='Assist')` rows alongside the
  `'Goal'` rows rather than collapsing them into the goal row's
  `assist_player_id` field.

- **Detail strings are stable.** FPL-origin rows use exactly these
  `detail` values (kept as constants in `services/fpl.py`):
  `Normal Goal (FPL)`, `Assist (FPL)`, `Yellow Card`, `Red Card`. The
  script's `--refresh` flag uses these (plus `minute IS NULL` for cards)
  to decide which existing rows are FPL-origin and safe to delete.

- **No quota cliff.** FPL doesn't publish a hard limit. The local client
  enforces a polite 0.4s spacing between calls and caches `bootstrap-static`
  for 5 minutes, so even a hot path (mapping + stats + events back-to-back)
  is well-behaved.

- **Junction table reuse.** FPL mappings are written under
  `provider='fpl'` for `entity_type` values `league`, `team`, `player`,
  and `match`. api-sports mappings stay under `provider='apisports'`. The
  unique constraints `(provider, entity_type, local_id)` and
  `(provider, entity_type, external_id)` keep both providers from
  stepping on each other.

## 7. What this integration does *not* touch

- `backend/services/data_ingestion.py`, `backend/services/apisports.py`,
  `backend/services/football_data_org.py`, `backend/scheduler.py`, and
  the frontend are unchanged.
- The new sync scripts are **manual / cron** — nothing wires them into the
  scheduler.
- No new pip dependencies. `requests` and (optional) `rapidfuzz` are
  already available.
