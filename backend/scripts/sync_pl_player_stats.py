"""Refresh local Player season stats from api-sports.io top scorers/assists.

Usage:
    cd backend && .venv/bin/python scripts/sync_pl_player_stats.py
    cd backend && .venv/bin/python scripts/sync_pl_player_stats.py --season 2024

Total api-sports.io calls: 2 (topscorers + topassists). Designed to be run on
a daily cron, e.g. ``0 4 * * *``.
"""

from __future__ import annotations

import argparse
import logging
import os
import sys
from typing import Any, Dict, Iterable, Optional

_THIS_DIR = os.path.dirname(os.path.abspath(__file__))
_BACKEND_DIR = os.path.dirname(_THIS_DIR)
if _BACKEND_DIR not in sys.path:
    sys.path.insert(0, _BACKEND_DIR)

try:
    from backend.database import SessionLocal
    from backend.models import Player, ProviderIdMap
    from backend.services.apisports import (
        ApisportsQuotaExceeded,
        calls_used_today,
        current_pl_season,
        get_topassists,
        get_topscorers,
    )
except ImportError:  # pragma: no cover
    from database import SessionLocal  # type: ignore
    from models import Player, ProviderIdMap  # type: ignore
    from services.apisports import (  # type: ignore
        ApisportsQuotaExceeded,
        calls_used_today,
        current_pl_season,
        get_topassists,
        get_topscorers,
    )

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")
logger = logging.getLogger("sync_pl_player_stats")

PROVIDER = "apisports"


def _to_int(value: Any) -> Optional[int]:
    if value is None or value == "":
        return None
    try:
        return int(float(value))
    except (TypeError, ValueError):
        return None


def _to_float(value: Any) -> Optional[float]:
    if value is None or value == "":
        return None
    try:
        return float(value)
    except (TypeError, ValueError):
        return None


def _resolve_local_player_id(db, apisports_player_id: int) -> Optional[int]:
    row = (
        db.query(ProviderIdMap)
        .filter(
            ProviderIdMap.provider == PROVIDER,
            ProviderIdMap.entity_type == "player",
            ProviderIdMap.external_id == apisports_player_id,
        )
        .first()
    )
    return row.local_id if row else None


def _apply_stats_to_player(player: Player, statistics_block: Dict[str, Any]) -> bool:
    """Update ``player`` from a single ``statistics[0]`` dict.

    Returns ``True`` if any field changed.
    """
    if not isinstance(statistics_block, dict):
        return False

    goals_block = statistics_block.get("goals") or {}
    games_block = statistics_block.get("games") or {}

    new_goals = _to_int(goals_block.get("total"))
    new_assists = _to_int(goals_block.get("assists"))
    new_rating = _to_float(games_block.get("rating"))
    new_minutes = _to_int(games_block.get("minutes"))

    changed = False
    if new_goals is not None and new_goals != player.goals_season:
        player.goals_season = new_goals
        changed = True
    if new_assists is not None and new_assists != player.assists_season:
        player.assists_season = new_assists
        changed = True
    if new_rating is not None and new_rating != player.rating_season:
        player.rating_season = new_rating
        changed = True
    if new_minutes is not None and new_minutes != player.minutes_played:
        player.minutes_played = new_minutes
        changed = True

    return changed


def _process_response(db, response: Iterable[Dict[str, Any]], counters: Dict[str, int]) -> None:
    for entry in response:
        if not isinstance(entry, dict):
            continue

        api_player = entry.get("player") or {}
        api_id = api_player.get("id")
        if api_id is None:
            counters["missing"] += 1
            continue

        local_id = _resolve_local_player_id(db, int(api_id))
        if local_id is None:
            counters["missing"] += 1
            logger.info("no mapping for api player id=%s name=%s", api_id, api_player.get("name"))
            continue

        local_player = db.query(Player).filter(Player.id == local_id).first()
        if local_player is None:
            counters["skipped"] += 1
            logger.info("local player id=%s vanished; skipping", local_id)
            continue

        statistics_list = entry.get("statistics") or []
        if not statistics_list:
            counters["skipped"] += 1
            continue

        if _apply_stats_to_player(local_player, statistics_list[0]):
            counters["updated"] += 1
        else:
            counters["skipped"] += 1


def main() -> int:
    parser = argparse.ArgumentParser(description="Sync PL player season stats from api-sports.io.")
    parser.add_argument(
        "--season",
        type=int,
        default=current_pl_season(),
        help="Season year (default: current PL season).",
    )
    args = parser.parse_args()

    logger.info("Syncing PL player stats for season=%d", args.season)

    db = SessionLocal()
    counters = {"updated": 0, "skipped": 0, "missing": 0}

    try:
        try:
            scorers = get_topscorers(args.season)
        except ApisportsQuotaExceeded as exc:
            logger.error("Quota exceeded on topscorers: %s", exc)
            return 1
        except Exception as exc:  # noqa: BLE001
            logger.error("Failed topscorers fetch: %s", exc)
            scorers = []

        try:
            assisters = get_topassists(args.season)
        except ApisportsQuotaExceeded as exc:
            logger.error("Quota exceeded on topassists: %s", exc)
            assisters = []
        except Exception as exc:  # noqa: BLE001
            logger.error("Failed topassists fetch: %s", exc)
            assisters = []

        _process_response(db, scorers, counters)
        _process_response(db, assisters, counters)

        db.commit()

        print("\nPlayer stats sync summary")
        print("=" * 50)
        print(f"updated: {counters['updated']}")
        print(f"skipped: {counters['skipped']}")
        print(f"missing: {counters['missing']}")
        print(f"api_calls_used: {calls_used_today()}")
        print("=" * 50)
        return 0
    except Exception:
        db.rollback()
        raise
    finally:
        db.close()


if __name__ == "__main__":
    raise SystemExit(main())
