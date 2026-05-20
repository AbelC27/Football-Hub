"""One-shot mapper: build local <-> Fantasy Premier League ID mappings.

Usage:
    cd backend && .venv/bin/python scripts/map_pl_fpl.py
    cd backend && .venv/bin/python scripts/map_pl_fpl.py --refresh
    cd backend && .venv/bin/python scripts/map_pl_fpl.py --threshold 75
    cd backend && .venv/bin/python scripts/map_pl_fpl.py --teams-only
    cd backend && .venv/bin/python scripts/map_pl_fpl.py --players-only

The script is idempotent: existing mappings are kept unless ``--refresh``
is passed. Total FPL network calls: 1 (a single ``bootstrap-static`` fetch).
"""

from __future__ import annotations

import argparse
import logging
import os
import sys
from typing import Any, Dict, List, Optional, Tuple

# Make ``backend`` importable when the script is invoked as
# ``backend/.venv/bin/python scripts/map_pl_fpl.py`` from the backend dir.
_THIS_DIR = os.path.dirname(os.path.abspath(__file__))
_BACKEND_DIR = os.path.dirname(_THIS_DIR)
if _BACKEND_DIR not in sys.path:
    sys.path.insert(0, _BACKEND_DIR)

try:
    from backend.database import SessionLocal
    from backend.models import League, Player, ProviderIdMap, Team
    from backend.services.fpl import (
        PL_FPL_LEAGUE_ID,
        PL_LOCAL_LEAGUE_ID,
        PROVIDER,
        get_bootstrap_static,
    )
except ImportError:  # pragma: no cover - direct script use
    from database import SessionLocal  # type: ignore
    from models import League, Player, ProviderIdMap, Team  # type: ignore
    from services.fpl import (  # type: ignore
        PL_FPL_LEAGUE_ID,
        PL_LOCAL_LEAGUE_ID,
        PROVIDER,
        get_bootstrap_static,
    )

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")
logger = logging.getLogger("map_pl_fpl")


# ---------------------------------------------------------------------------
# Fuzzy matching helpers (mirrors map_pl_apisports.py)
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


# Manual alias table for FPL short/display names that the fuzzy matcher
# routinely misses. Keys are the *local* canonical names (as stored in the
# `teams` table). Values are FPL `name` / `short_name` strings (any case)
# that should be treated as exact matches. Add entries here whenever a new
# club joins the PL with a wildly abbreviated FPL short_name.
LOCAL_TEAM_ALIASES: Dict[str, List[str]] = {
    "Manchester City FC": ["Man City", "Manchester City"],
    "Manchester United FC": ["Man Utd", "Man United", "Manchester United"],
    "Tottenham Hotspur FC": ["Spurs", "Tottenham"],
    "Wolverhampton Wanderers FC": ["Wolves", "Wolverhampton"],
    "Newcastle United FC": ["Newcastle"],
    "Nottingham Forest FC": ["Forest", "Nott'm Forest"],
    "Brighton & Hove Albion FC": ["Brighton"],
    "AFC Bournemouth": ["Bournemouth"],
    "West Ham United FC": ["West Ham"],
    "Leicester City FC": ["Leicester"],
    "Crystal Palace FC": ["Palace", "Crystal Palace"],
    "Sheffield United FC": ["Sheffield Utd", "Sheffield United"],
    "Leeds United FC": ["Leeds", "Leeds United"],
    "Ipswich Town FC": ["Ipswich"],
}


def _alias_match(local_name: str, *fpl_candidates: str) -> bool:
    """Return True iff any FPL candidate matches a known alias of local_name."""
    aliases = LOCAL_TEAM_ALIASES.get(local_name)
    if not aliases:
        return False
    candidates = {_normalize(c) for c in fpl_candidates if c}
    if not candidates:
        return False
    return any(_normalize(alias) in candidates for alias in aliases)


# ---------------------------------------------------------------------------
# Mapping upsert (same shape as map_pl_apisports._upsert_mapping)
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
        db.add(
            ProviderIdMap(
                provider=PROVIDER,
                entity_type=entity_type,
                local_id=local_id,
                external_id=external_id,
                confidence=confidence,
                notes=notes,
            )
        )
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


def _best_team_match(api_name: str, api_short: str, local_teams: List[Team]) -> Tuple[Optional[Team], float]:
    """Return the best local team match using the higher of name/short_name scores."""
    normalized_api = _normalize(api_name)
    exact = next((t for t in local_teams if _normalize(t.name) == normalized_api), None)
    if exact is not None:
        return exact, 100.0

    # Manual alias table for FPL <-> football-data.org name quirks. If we
    # find a hit here, treat it as a perfect match.
    aliased = next(
        (t for t in local_teams if _alias_match(t.name or "", api_name, api_short)),
        None,
    )
    if aliased is not None:
        return aliased, 100.0

    best_local: Optional[Team] = None
    best_score = 0.0
    for local_team in local_teams:
        score_full = _score(api_name, local_team.name or "")
        score_short = _score(api_short, local_team.name or "")
        score = max(score_full, score_short)
        if score > best_score:
            best_score = score
            best_local = local_team
    return best_local, best_score


def _map_teams(
    db,
    fpl_teams: List[Dict[str, Any]],
    threshold: int,
    refresh: bool,
) -> Dict[int, int]:
    """Build fpl_team_id -> local_team_id mapping."""
    local_teams = db.query(Team).filter(Team.league_id == PL_LOCAL_LEAGUE_ID).all()
    if not local_teams:
        logger.warning("No local PL teams found (league_id=%d).", PL_LOCAL_LEAGUE_ID)
        return {}

    mapped: Dict[int, int] = {}
    summary_rows: List[Tuple[str, str, str, float]] = []
    matched_count = 0
    unmatched_count = 0

    for entry in fpl_teams:
        fpl_id = entry.get("id")
        api_name = entry.get("name") or ""
        api_short = entry.get("short_name") or ""
        if fpl_id is None:
            continue

        best_local, best_score = _best_team_match(api_name, api_short, local_teams)

        if best_local is None or best_score < threshold:
            summary_rows.append((api_name, "—", "UNMATCHED", best_score))
            logger.warning(
                "team unmatched: fpl='%s' (short='%s') best_local='%s' score=%.1f (threshold=%d)",
                api_name,
                api_short,
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
                external_id=int(fpl_id),
                confidence=round(best_score, 2),
                notes=f"name='{api_name}' short='{api_short}' -> local='{best_local.name}'",
                refresh=refresh,
            )
        except Exception as exc:  # noqa: BLE001
            db.rollback()
            logger.exception("Failed to upsert team mapping for %s: %s", api_name, exc)
            unmatched_count += 1
            continue

        mapped[int(fpl_id)] = best_local.id
        matched_count += 1
        summary_rows.append((api_name, best_local.name, status, best_score))

    db.commit()

    print("\nTeam mapping summary (FPL)")
    print("=" * 78)
    print(f"{'FPL name':<32} {'local name':<28} {'status':<14} {'score':>5}")
    print("-" * 78)
    for api_name, local_name, status, score in summary_rows:
        print(f"{api_name[:32]:<32} {local_name[:28]:<28} {status:<14} {score:>5.1f}")
    print("-" * 78)
    print(f"matched={matched_count} unmatched={unmatched_count}\n")

    return mapped


# ---------------------------------------------------------------------------
# Player mapping
# ---------------------------------------------------------------------------


def _existing_team_map(db) -> Dict[int, int]:
    rows = (
        db.query(ProviderIdMap)
        .filter(
            ProviderIdMap.provider == PROVIDER,
            ProviderIdMap.entity_type == "team",
        )
        .all()
    )
    return {int(r.external_id): int(r.local_id) for r in rows}


def _best_player_match(
    candidate_full: str,
    web_name: str,
    local_players: List[Player],
) -> Tuple[Optional[Player], float]:
    """Return the best local player and the higher score of the two attempted comparisons."""
    normalized_full = _normalize(candidate_full)
    exact = next((p for p in local_players if _normalize(p.name) == normalized_full), None)
    if exact is not None:
        return exact, 100.0

    best_local: Optional[Player] = None
    best_score = 0.0
    for local_player in local_players:
        score_full = _score(candidate_full, local_player.name or "")
        score_web = _score(web_name, local_player.name or "")
        score = max(score_full, score_web)
        if score > best_score:
            best_score = score
            best_local = local_player
    return best_local, best_score


def _map_players(
    db,
    elements: List[Dict[str, Any]],
    fpl_team_to_local: Dict[int, int],
    threshold: int,
    refresh: bool,
) -> Tuple[int, int]:
    if not fpl_team_to_local:
        logger.warning("No FPL->local team mapping available; cannot scope player matching.")
        return 0, 0

    # Pre-load all PL local players grouped by team for cheap candidate lookup.
    pl_team_ids = list(set(fpl_team_to_local.values()))
    if not pl_team_ids:
        return 0, 0

    local_players = db.query(Player).filter(Player.team_id.in_(pl_team_ids)).all()
    by_team: Dict[int, List[Player]] = {}
    for player in local_players:
        by_team.setdefault(int(player.team_id), []).append(player)

    matched = 0
    unmatched = 0

    for element in elements:
        fpl_player_id = element.get("id")
        fpl_team_id = element.get("team")
        if fpl_player_id is None or fpl_team_id is None:
            continue

        local_team_id = fpl_team_to_local.get(int(fpl_team_id))
        if local_team_id is None:
            unmatched += 1
            continue

        candidates = by_team.get(local_team_id, [])
        if not candidates:
            unmatched += 1
            continue

        first_name = (element.get("first_name") or "").strip()
        second_name = (element.get("second_name") or "").strip()
        web_name = (element.get("web_name") or "").strip()
        candidate_full = f"{first_name} {second_name}".strip()

        best_local, best_score = _best_player_match(candidate_full, web_name, candidates)

        if best_local is None or best_score < threshold:
            logger.info(
                "player unmatched: fpl_id=%s full='%s' web='%s' team_id=%d best_local='%s' score=%.1f",
                fpl_player_id,
                candidate_full,
                web_name,
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
                external_id=int(fpl_player_id),
                confidence=round(best_score, 2),
                notes=f"full='{candidate_full}' web='{web_name}' -> local='{best_local.name}'",
                refresh=refresh,
            )
            matched += 1
        except Exception as exc:  # noqa: BLE001
            db.rollback()
            logger.exception("Failed to upsert player mapping for %s: %s", candidate_full, exc)
            unmatched += 1

    db.commit()
    return matched, unmatched


# ---------------------------------------------------------------------------
# Entrypoint
# ---------------------------------------------------------------------------


def main() -> int:
    parser = argparse.ArgumentParser(description="Map PL teams/players to FPL IDs.")
    parser.add_argument("--refresh", action="store_true", help="Overwrite existing mappings.")
    parser.add_argument(
        "--threshold",
        type=int,
        default=85,
        help="Fuzzy match threshold 0..100 for player/team names (default: 85).",
    )
    parser.add_argument(
        "--players-only",
        action="store_true",
        help="Skip the team mapping pass (assume teams are already mapped).",
    )
    parser.add_argument(
        "--teams-only",
        action="store_true",
        help="Skip the player mapping pass.",
    )
    args = parser.parse_args()

    if args.players_only and args.teams_only:
        parser.error("--players-only and --teams-only are mutually exclusive.")

    logger.info("Using fuzzy backend: %s", _FUZZ_BACKEND)
    logger.info(
        "threshold=%d refresh=%s players_only=%s teams_only=%s",
        args.threshold,
        args.refresh,
        args.players_only,
        args.teams_only,
    )

    db = SessionLocal()
    network_calls = 0
    try:
        league = db.query(League).filter(League.id == PL_LOCAL_LEAGUE_ID).first()
        if league is None:
            logger.error(
                "Premier League (id=%d) is not present in the local database. "
                "Seed the league first, then re-run this script.",
                PL_LOCAL_LEAGUE_ID,
            )
            return 2

        # League pin. FPL doesn't expose a competition id, so we persist 1
        # (PL is the only competition this API serves) — see services/fpl.py.
        try:
            _, league_status = _upsert_mapping(
                db,
                entity_type="league",
                local_id=PL_LOCAL_LEAGUE_ID,
                external_id=PL_FPL_LEAGUE_ID,
                confidence=100.0,
                notes="FPL has no competition id; persisting 1 as placeholder.",
                refresh=args.refresh,
            )
            db.commit()
            logger.info("league mapping: %s", league_status)
        except Exception as exc:  # noqa: BLE001
            db.rollback()
            logger.exception("Failed to upsert league mapping: %s", exc)

        try:
            bootstrap = get_bootstrap_static(force_refresh=True)
            network_calls += 1
        except Exception as exc:  # noqa: BLE001
            logger.exception("Failed to fetch FPL bootstrap-static: %s", exc)
            return 1

        fpl_teams = bootstrap.get("teams") or []
        elements = bootstrap.get("elements") or []
        logger.info("bootstrap-static: %d teams, %d elements", len(fpl_teams), len(elements))

        if args.players_only:
            team_map = _existing_team_map(db)
            logger.info("players-only mode: reusing %d existing FPL team mappings.", len(team_map))
        else:
            team_map = _map_teams(db, fpl_teams, args.threshold, args.refresh)

        if args.teams_only:
            player_matched = player_unmatched = 0
        elif not team_map:
            logger.warning("No teams mapped; skipping player pass.")
            player_matched = player_unmatched = 0
        else:
            player_matched, player_unmatched = _map_players(
                db, elements, team_map, args.threshold, args.refresh
            )

        print("\nFinal summary (FPL)")
        print("=" * 60)
        print(f"teams_mapped:        {len(team_map)}")
        print(f"players_matched:     {player_matched}")
        print(f"players_unmatched:   {player_unmatched}")
        print(f"network_calls:       {network_calls}")
        print("=" * 60)
        return 0
    finally:
        db.close()


if __name__ == "__main__":
    raise SystemExit(main())
