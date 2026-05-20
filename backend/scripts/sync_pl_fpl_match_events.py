"""Backfill local ``MatchEvent`` rows from FPL fixtures.

Usage:
    cd backend && .venv/bin/python scripts/sync_pl_fpl_match_events.py
    cd backend && .venv/bin/python scripts/sync_pl_fpl_match_events.py --event 28
    cd backend && .venv/bin/python scripts/sync_pl_fpl_match_events.py --refresh
    cd backend && .venv/bin/python scripts/sync_pl_fpl_match_events.py --limit 10

By default this walks every finished FPL fixture for the current season
(``--all-finished``) and persists ``MatchEvent`` rows for the local
``Match`` it can be linked to. Pass ``--event N`` to scope the run to a
single gameweek instead.

Note on data shape: FPL fixture stats are aggregated per player per fixture
(no minute-by-minute timing). Goals and assists are emitted as separate
``MatchEvent`` rows since FPL does not pair scorers with assisters. Card
rows are emitted with ``minute=None`` (FPL doesn't surface card timing).

Total FPL network calls: 1 (single ``/fixtures/`` or ``/fixtures/?event=N``).
"""

from __future__ import annotations

import argparse
import datetime as _dt
import logging
import os
import sys
from typing import Any, Dict, List, Optional, Tuple

_THIS_DIR = os.path.dirname(os.path.abspath(__file__))
_BACKEND_DIR = os.path.dirname(_THIS_DIR)
if _BACKEND_DIR not in sys.path:
    sys.path.insert(0, _BACKEND_DIR)

try:
    from backend.database import SessionLocal
    from backend.models import Match, MatchEvent, Player, ProviderIdMap
    from backend.services.fpl import (
        DETAIL_ASSIST,
        DETAIL_GOAL,
        DETAIL_RED_CARD,
        DETAIL_YELLOW_CARD,
        PL_LOCAL_LEAGUE_ID,
        PROVIDER,
        _emit_match_events_from_stats,
        _kickoff_to_dt,
        get_all_fixtures,
        get_gameweek_fixtures,
    )
except ImportError:  # pragma: no cover
    from database import SessionLocal  # type: ignore
    from models import Match, MatchEvent, Player, ProviderIdMap  # type: ignore
    from services.fpl import (  # type: ignore
        DETAIL_ASSIST,
        DETAIL_GOAL,
        DETAIL_RED_CARD,
        DETAIL_YELLOW_CARD,
        PL_LOCAL_LEAGUE_ID,
        PROVIDER,
        _emit_match_events_from_stats,
        _kickoff_to_dt,
        get_all_fixtures,
        get_gameweek_fixtures,
    )

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")
logger = logging.getLogger("sync_pl_fpl_match_events")

FINISHED_STATUSES = {"FT", "AET", "PEN"}
FPL_DETAILS = {DETAIL_GOAL, DETAIL_ASSIST, DETAIL_YELLOW_CARD, DETAIL_RED_CARD}


def _has_existing_events(db, match_id: int) -> bool:
    return (
        db.query(MatchEvent.id)
        .filter(MatchEvent.match_id == match_id)
        .first()
        is not None
    )


def _delete_fpl_origin_events(db, match_id: int) -> int:
    rows = db.query(MatchEvent).filter(MatchEvent.match_id == match_id).all()
    deleted = 0
    for row in rows:
        if row.detail in {DETAIL_GOAL, DETAIL_ASSIST}:
            db.delete(row)
            deleted += 1
        elif row.detail in {DETAIL_YELLOW_CARD, DETAIL_RED_CARD} and row.minute is None:
            db.delete(row)
            deleted += 1
    if deleted:
        db.flush()
    return deleted


def _build_fpl_player_lookup(
    db,
    fixture: Dict[str, Any],
) -> Tuple[Dict[int, int], Dict[int, str]]:
    """Pre-load mappings + display names for every player referenced by ``fixture['stats']``."""
    fpl_player_ids: List[int] = []
    for block in fixture.get("stats") or []:
        for side in ("h", "a"):
            for entry in (block.get(side) or []):
                fpid = entry.get("element")
                if fpid is not None:
                    fpl_player_ids.append(int(fpid))

    if not fpl_player_ids:
        return {}, {}

    rows = (
        db.query(ProviderIdMap)
        .filter(
            ProviderIdMap.provider == PROVIDER,
            ProviderIdMap.entity_type == "player",
            ProviderIdMap.external_id.in_(list(set(fpl_player_ids))),
        )
        .all()
    )
    fpl_to_local = {int(r.external_id): int(r.local_id) for r in rows}

    name_lookup: Dict[int, str] = {}
    if fpl_to_local:
        local_ids = list(fpl_to_local.values())
        local_players = db.query(Player).filter(Player.id.in_(local_ids)).all()
        local_id_to_name = {p.id: p.name for p in local_players}
        for fpl_id, local_id in fpl_to_local.items():
            name = local_id_to_name.get(local_id)
            if name:
                name_lookup[fpl_id] = name

    return fpl_to_local, name_lookup


def _ensure_match_mapping(db, match_id: int, fpl_fixture_id: int, notes: str) -> None:
    existing = (
        db.query(ProviderIdMap)
        .filter(
            ProviderIdMap.provider == PROVIDER,
            ProviderIdMap.entity_type == "match",
            ProviderIdMap.local_id == match_id,
        )
        .first()
    )
    if existing is not None:
        return
    db.add(
        ProviderIdMap(
            provider=PROVIDER,
            entity_type="match",
            local_id=match_id,
            external_id=int(fpl_fixture_id),
            confidence=100.0,
            notes=notes,
        )
    )


def _load_finished_pl_matches(db) -> List[Match]:
    return (
        db.query(Match)
        .filter(
            Match.league_id == PL_LOCAL_LEAGUE_ID,
            Match.status.in_(list(FINISHED_STATUSES)),
        )
        .order_by(Match.start_time.asc())
        .all()
    )


def _process_fixture(
    db,
    fixture: Dict[str, Any],
    *,
    finished_matches_by_id: Dict[int, Match],
    refresh: bool,
    counters: Dict[str, int],
    match_window_hours: int,
) -> None:
    if not fixture.get("finished"):
        counters["skipped"] += 1
        return

    fpl_id = fixture.get("id")
    if fpl_id is None:
        counters["missing"] += 1
        return
    fpl_id = int(fpl_id)

    # Try the existing ProviderIdMap mapping first.
    map_row = (
        db.query(ProviderIdMap)
        .filter(
            ProviderIdMap.provider == PROVIDER,
            ProviderIdMap.entity_type == "match",
            ProviderIdMap.external_id == fpl_id,
        )
        .first()
    )

    match: Optional[Match] = None
    if map_row is not None:
        match = finished_matches_by_id.get(int(map_row.local_id))

    if match is None:
        # Fallback: find a candidate Match by team mapping + kickoff window.
        match = _find_match_by_teams_and_window(
            db,
            fixture,
            finished_matches_by_id,
            match_window_hours,
        )
        if match is not None:
            _ensure_match_mapping(
                db,
                match.id,
                fpl_id,
                notes=f"resolved via team+kickoff window (gameweek={fixture.get('event')})",
            )

    if match is None:
        counters["missing"] += 1
        return

    if not refresh and _has_existing_events(db, match.id):
        counters["skipped"] += 1
        return

    if refresh:
        _delete_fpl_origin_events(db, match.id)

    fpl_to_local, name_lookup = _build_fpl_player_lookup(db, fixture)
    rows = _emit_match_events_from_stats(match, fixture, fpl_to_local, name_lookup)

    for kwargs in rows:
        db.add(MatchEvent(**kwargs))

    counters["created"] += len(rows)
    counters["processed"] += 1


def _find_match_by_teams_and_window(
    db,
    fixture: Dict[str, Any],
    finished_matches_by_id: Dict[int, Match],
    match_window_hours: int,
) -> Optional[Match]:
    team_h = fixture.get("team_h")
    team_a = fixture.get("team_a")
    kickoff_dt = _kickoff_to_dt(fixture.get("kickoff_time"))
    if team_h is None or team_a is None or kickoff_dt is None:
        return None

    team_rows = (
        db.query(ProviderIdMap)
        .filter(
            ProviderIdMap.provider == PROVIDER,
            ProviderIdMap.entity_type == "team",
            ProviderIdMap.external_id.in_([int(team_h), int(team_a)]),
        )
        .all()
    )
    fpl_to_local_team = {int(r.external_id): int(r.local_id) for r in team_rows}
    local_home = fpl_to_local_team.get(int(team_h))
    local_away = fpl_to_local_team.get(int(team_a))
    if local_home is None or local_away is None:
        return None

    window = _dt.timedelta(hours=int(match_window_hours))
    candidates: List[Match] = []
    for match in finished_matches_by_id.values():
        if match.home_team_id != local_home or match.away_team_id != local_away:
            continue
        if not match.start_time:
            continue
        match_dt = match.start_time
        if match_dt.tzinfo is None:
            match_dt = match_dt.replace(tzinfo=_dt.timezone.utc)
        if abs(match_dt - kickoff_dt) <= window:
            candidates.append(match)

    if len(candidates) != 1:
        return None
    return candidates[0]


def main() -> int:
    parser = argparse.ArgumentParser(description="Sync MatchEvent rows from FPL fixture stats.")
    group = parser.add_mutually_exclusive_group()
    group.add_argument("--event", type=int, default=None, help="Single gameweek to process.")
    group.add_argument(
        "--all-finished",
        action="store_true",
        help="Process every finished fixture in the current season (default behavior).",
    )
    parser.add_argument(
        "--limit",
        type=int,
        default=50,
        help="Cap the number of fixtures processed in this run (default: 50).",
    )
    parser.add_argument(
        "--refresh",
        action="store_true",
        help="Delete pre-existing FPL-origin MatchEvent rows for a match before re-inserting.",
    )
    parser.add_argument(
        "--match-window-hours",
        type=int,
        default=6,
        help="Tolerance window when matching FPL fixture kickoff to local Match.start_time (default: 6).",
    )
    args = parser.parse_args()

    use_gameweek = args.event is not None
    logger.info(
        "mode=%s limit=%d refresh=%s window_hours=%d",
        f"gameweek={args.event}" if use_gameweek else "all-finished",
        args.limit,
        args.refresh,
        args.match_window_hours,
    )

    db = SessionLocal()
    counters = {"processed": 0, "created": 0, "skipped": 0, "missing": 0}
    network_calls = 0

    try:
        try:
            if use_gameweek:
                fixtures = get_gameweek_fixtures(int(args.event))
            else:
                fixtures = get_all_fixtures()
            network_calls += 1
        except Exception as exc:  # noqa: BLE001
            logger.exception("FPL fixtures fetch failed: %s", exc)
            return 1

        finished_matches = _load_finished_pl_matches(db)
        finished_by_id = {m.id: m for m in finished_matches}

        capped = 0
        for fixture in fixtures:
            if capped >= args.limit:
                logger.info("--limit %d reached; stopping.", args.limit)
                break
            try:
                before_processed = counters["processed"]
                _process_fixture(
                    db,
                    fixture,
                    finished_matches_by_id=finished_by_id,
                    refresh=args.refresh,
                    counters=counters,
                    match_window_hours=args.match_window_hours,
                )
                if counters["processed"] > before_processed:
                    capped += 1
            except Exception as exc:  # noqa: BLE001
                db.rollback()
                logger.exception(
                    "Failed to process FPL fixture %s: %s",
                    fixture.get("id"),
                    exc,
                )
                counters["missing"] += 1

        db.commit()

        print("\nFPL match events sync summary")
        print("=" * 50)
        print(f"processed:      {counters['processed']}")
        print(f"created (rows): {counters['created']}")
        print(f"skipped:        {counters['skipped']}")
        print(f"missing:        {counters['missing']}")
        print(f"network_calls:  {network_calls}")
        print("=" * 50)
        return 0
    except Exception:
        db.rollback()
        raise
    finally:
        db.close()


if __name__ == "__main__":
    raise SystemExit(main())
