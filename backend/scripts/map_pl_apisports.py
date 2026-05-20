"""One-shot mapper: build local <-> api-sports.io ID mappings for the PL.

Usage:
    cd backend && .venv/bin/python scripts/map_pl_apisports.py
    cd backend && .venv/bin/python scripts/map_pl_apisports.py --season 2024
    cd backend && .venv/bin/python scripts/map_pl_apisports.py --refresh
    cd backend && .venv/bin/python scripts/map_pl_apisports.py --threshold 90

The script is idempotent: existing mappings are kept unless ``--refresh`` is
passed. Total api-sports.io calls: ~21 (1 league teams + 20 squad fetches).
"""

from __future__ import annotations

import argparse
import logging
import os
import sys
from typing import Dict, List, Optional, Tuple

# Make ``backend`` importable when the script is invoked as
# ``backend/.venv/bin/python scripts/map_pl_apisports.py`` from the backend
# directory.
_THIS_DIR = os.path.dirname(os.path.abspath(__file__))
_BACKEND_DIR = os.path.dirname(_THIS_DIR)
if _BACKEND_DIR not in sys.path:
    sys.path.insert(0, _BACKEND_DIR)

try:
    from backend.database import SessionLocal
    from backend.models import League, Player, ProviderIdMap, Team
    from backend.services.apisports import (
        ApisportsQuotaExceeded,
        calls_used_today,
        current_pl_season,
        get_pl_teams,
        get_team_squad,
    )
except ImportError:  # pragma: no cover - fallback for direct script use
    from database import SessionLocal  # type: ignore
    from models import League, Player, ProviderIdMap, Team  # type: ignore
    from services.apisports import (  # type: ignore
        ApisportsQuotaExceeded,
        calls_used_today,
        current_pl_season,
        get_pl_teams,
        get_team_squad,
    )

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")
logger = logging.getLogger("map_pl_apisports")

PROVIDER = "apisports"
PL_LOCAL_ID = 2021      # football-data.org id
PL_EXTERNAL_ID = 39     # api-sports id


# ---------------------------------------------------------------------------
# Fuzzy matching helpers
# ---------------------------------------------------------------------------

try:
    from rapidfuzz import fuzz as _rf_fuzz  # type: ignore

    def _score(a: str, b: str) -> float:
        return float(_rf_fuzz.token_set_ratio(a or "", b or ""))

    _FUZZ_BACKEND = "rapidfuzz"
except Exception:  # noqa: BLE001 - rapidfuzz is optional
    from difflib import SequenceMatcher

    def _score(a: str, b: str) -> float:
        return SequenceMatcher(None, (a or "").lower(), (b or "").lower()).ratio() * 100.0

    _FUZZ_BACKEND = "difflib"


def _normalize(name: str) -> str:
    return (name or "").strip().lower()


# ---------------------------------------------------------------------------
# Mapping upsert
# ---------------------------------------------------------------------------


def _upsert_mapping(
    db,
    *,
    entity_type: str,
    local_id: int,
    external_id: int,
    confidence: Optional[float],
    notes: Optional[str],
    refresh: bool,
) -> Tuple[bool, str]:
    """Insert or update a ``ProviderIdMap`` row.

    Returns ``(changed, status)`` where ``status`` is one of ``inserted``,
    ``updated``, ``skipped_existing``.
    """
    existing = (
        db.query(ProviderIdMap)
        .filter(
            ProviderIdMap.provider == PROVIDER,
            ProviderIdMap.entity_type == entity_type,
            ProviderIdMap.local_id == local_id,
        )
        .first()
    )

    if existing is None:
        # Also check by external id (the other unique key) so we never crash
        # on a constraint violation.
        existing = (
            db.query(ProviderIdMap)
            .filter(
                ProviderIdMap.provider == PROVIDER,
                ProviderIdMap.entity_type == entity_type,
                ProviderIdMap.external_id == external_id,
            )
            .first()
        )

    if existing is not None and not refresh:
        return False, "skipped_existing"

    if existing is None:
        row = ProviderIdMap(
            provider=PROVIDER,
            entity_type=entity_type,
            local_id=local_id,
            external_id=external_id,
            confidence=confidence,
            notes=notes,
        )
        db.add(row)
        db.flush()
        return True, "inserted"

    existing.local_id = local_id
    existing.external_id = external_id
    existing.confidence = confidence
    existing.notes = notes
    db.flush()
    return True, "updated"


# ---------------------------------------------------------------------------
# Team mapping
# ---------------------------------------------------------------------------


def _map_teams(db, season: int, threshold: int, refresh: bool) -> Dict[int, int]:
    """Build apisports_team_id -> local_team_id mapping.

    Returns the dict of mapped teams (used for the squad pass).
    """
    apisports_teams: List[Dict] = []
    try:
        apisports_teams = get_pl_teams(season)
    except ApisportsQuotaExceeded as exc:
        logger.error("Quota exceeded fetching teams: %s", exc)
        return {}
    except Exception as exc:  # noqa: BLE001 - keep going on partial failure
        logger.error("Failed to fetch api-sports teams: %s", exc)
        return {}

    local_teams = db.query(Team).filter(Team.league_id == PL_LOCAL_ID).all()
    if not local_teams:
        logger.warning("No local PL teams found (league_id=%d).", PL_LOCAL_ID)
        return {}

    mapped: Dict[int, int] = {}
    summary_rows: List[Tuple[str, str, str, float]] = []
    matched_count = 0
    unmatched_count = 0

    for entry in apisports_teams:
        api_team = (entry or {}).get("team", {}) or {}
        api_id = api_team.get("id")
        api_name = api_team.get("name") or ""
        if api_id is None:
            continue

        # Try exact name match first.
        normalized_api = _normalize(api_name)
        exact = next((t for t in local_teams if _normalize(t.name) == normalized_api), None)

        if exact is not None:
            best_local = exact
            best_score = 100.0
        else:
            best_local = None
            best_score = 0.0
            for local_team in local_teams:
                score = _score(api_name, local_team.name or "")
                if score > best_score:
                    best_score = score
                    best_local = local_team

        if best_local is None or best_score < threshold:
            summary_rows.append((api_name, "—", "UNMATCHED", best_score))
            logger.warning(
                "team unmatched: api='%s' best_local='%s' score=%.1f (threshold=%d)",
                api_name,
                best_local.name if best_local else None,
                best_score,
                threshold,
            )
            unmatched_count += 1
            continue

        try:
            _, status = _upsert_mapping(
                db,
                entity_type="team",
                local_id=best_local.id,
                external_id=int(api_id),
                confidence=round(best_score, 2),
                notes=f"name='{api_name}' -> local='{best_local.name}'",
                refresh=refresh,
            )
        except Exception as exc:  # noqa: BLE001
            db.rollback()
            logger.error("Failed to upsert team mapping for %s: %s", api_name, exc)
            unmatched_count += 1
            continue

        mapped[int(api_id)] = best_local.id
        matched_count += 1
        summary_rows.append((api_name, best_local.name, status, best_score))

    db.commit()

    # Print a tidy summary table.
    print("\nTeam mapping summary")
    print("=" * 78)
    print(f"{'api-sports name':<32} {'local name':<28} {'status':<14} {'score':>5}")
    print("-" * 78)
    for api_name, local_name, status, score in summary_rows:
        print(f"{api_name[:32]:<32} {local_name[:28]:<28} {status:<14} {score:>5.1f}")
    print("-" * 78)
    print(f"matched={matched_count} unmatched={unmatched_count}\n")

    return mapped


# ---------------------------------------------------------------------------
# Player mapping
# ---------------------------------------------------------------------------


def _map_players(
    db,
    team_map: Dict[int, int],
    threshold: int,
    refresh: bool,
) -> Tuple[int, int]:
    """For each mapped team, fetch its squad and fuzzy-match players.

    Returns ``(matched_count, unmatched_count)``.
    """
    matched = 0
    unmatched = 0

    for apisports_team_id, local_team_id in team_map.items():
        try:
            squad = get_team_squad(apisports_team_id)
        except ApisportsQuotaExceeded as exc:
            logger.error("Quota exceeded fetching squad for team %d: %s", apisports_team_id, exc)
            break
        except Exception as exc:  # noqa: BLE001 - keep going on partial failure
            logger.error("Failed to fetch squad for api-sports team %d: %s", apisports_team_id, exc)
            continue

        local_players = db.query(Player).filter(Player.team_id == local_team_id).all()
        if not local_players:
            logger.info("No local players for team_id=%d; skipping squad of %d.", local_team_id, len(squad))
            unmatched += len(squad)
            continue

        for api_player in squad:
            api_id = (api_player or {}).get("id")
            api_name = (api_player or {}).get("name") or ""
            if api_id is None:
                continue

            best_local = None
            best_score = 0.0
            for local_player in local_players:
                score = _score(api_name, local_player.name or "")
                if score > best_score:
                    best_score = score
                    best_local = local_player

            if best_local is None or best_score < threshold:
                logger.info(
                    "player unmatched: api='%s' team_id=%d best_local='%s' score=%.1f",
                    api_name,
                    local_team_id,
                    best_local.name if best_local else None,
                    best_score,
                )
                unmatched += 1
                continue

            try:
                _, _status = _upsert_mapping(
                    db,
                    entity_type="player",
                    local_id=best_local.id,
                    external_id=int(api_id),
                    confidence=round(best_score, 2),
                    notes=f"name='{api_name}' -> local='{best_local.name}'",
                    refresh=refresh,
                )
                matched += 1
            except Exception as exc:  # noqa: BLE001
                db.rollback()
                logger.error("Failed to upsert player mapping for %s: %s", api_name, exc)
                unmatched += 1

        db.commit()

    return matched, unmatched


# ---------------------------------------------------------------------------
# Entrypoint
# ---------------------------------------------------------------------------


def main() -> int:
    parser = argparse.ArgumentParser(description="Map PL teams/players to api-sports IDs.")
    parser.add_argument("--season", type=int, default=current_pl_season(), help="PL season year (default: current).")
    parser.add_argument("--refresh", action="store_true", help="Overwrite existing mappings.")
    parser.add_argument(
        "--threshold",
        type=int,
        default=85,
        help="Fuzzy match threshold 0..100 for player/team names (default: 85).",
    )
    args = parser.parse_args()

    logger.info("Using fuzzy backend: %s", _FUZZ_BACKEND)
    logger.info("Season=%d threshold=%d refresh=%s", args.season, args.threshold, args.refresh)

    db = SessionLocal()
    try:
        league = db.query(League).filter(League.id == PL_LOCAL_ID).first()
        if league is None:
            logger.error(
                "Premier League (id=%d) is not present in the local database. "
                "Seed the league first, then re-run this script.",
                PL_LOCAL_ID,
            )
            return 2

        # Pin the league mapping first.
        try:
            _, league_status = _upsert_mapping(
                db,
                entity_type="league",
                local_id=PL_LOCAL_ID,
                external_id=PL_EXTERNAL_ID,
                confidence=100.0,
                notes="Premier League",
                refresh=args.refresh,
            )
            db.commit()
            logger.info("league mapping: %s", league_status)
        except Exception as exc:  # noqa: BLE001
            db.rollback()
            logger.error("Failed to upsert league mapping: %s", exc)

        team_map = _map_teams(db, args.season, args.threshold, args.refresh)

        if not team_map:
            logger.warning("No teams mapped; skipping player pass.")
            player_matched = player_unmatched = 0
        else:
            player_matched, player_unmatched = _map_players(
                db, team_map, args.threshold, args.refresh
            )

        print("\nFinal summary")
        print("=" * 60)
        print(f"teams_mapped:        {len(team_map)}")
        print(f"players_matched:     {player_matched}")
        print(f"players_unmatched:   {player_unmatched}")
        print(f"api_calls_used:      {calls_used_today()}")
        print("=" * 60)
        return 0
    finally:
        db.close()


if __name__ == "__main__":
    raise SystemExit(main())
