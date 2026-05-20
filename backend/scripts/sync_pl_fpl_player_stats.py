"""Refresh local Player season stats from the FPL bootstrap-static endpoint.

Usage:
    cd backend && .venv/bin/python scripts/sync_pl_fpl_player_stats.py
    cd backend && .venv/bin/python scripts/sync_pl_fpl_player_stats.py --mark-confidence-floor 85

Total FPL network calls: 1. Designed to be run on a daily cron, e.g.
``15 4 * * *`` (15 minutes after the api-sports cron, so the two providers
don't pile on at the same time).

What gets updated:

Counting stats:
* ``Player.goals_season`` <- ``element.goals_scored``
* ``Player.assists_season`` <- ``element.assists``
* ``Player.minutes_played`` <- ``element.minutes``

FPL signal fields (used to compute the overall rating):
* ``Player.fpl_total_points``    <- ``element.total_points``
* ``Player.fpl_points_per_game`` <- ``element.points_per_game``
* ``Player.fpl_form``            <- ``element.form``
* ``Player.fpl_ict_index``       <- ``element.ict_index``
* ``Player.fpl_influence``       <- ``element.influence``
* ``Player.fpl_creativity``      <- ``element.creativity``
* ``Player.fpl_threat``          <- ``element.threat``
* ``Player.fpl_element_type``    <- ``element.element_type`` (1=GK 2=DEF 3=MID 4=FWD)

Photo:
* ``Player.photo_url`` <- the FPL CDN asset
  ``https://resources.premierleague.com/premierleague/photos/players/250x250/p{id}.png``
  derived from ``element.photo``. Only overwritten when the FPL element
  references a different file; never cleared (we keep the last good URL
  even after a player loses their FPL listing).

``Player.rating_season`` is NOT touched — FPL doesn't surface a season rating
and we don't want to clobber anything api-sports may have populated.
"""

from __future__ import annotations

import argparse
import logging
import os
import sys
from typing import Any, Dict, Optional

_THIS_DIR = os.path.dirname(os.path.abspath(__file__))
_BACKEND_DIR = os.path.dirname(_THIS_DIR)
if _BACKEND_DIR not in sys.path:
    sys.path.insert(0, _BACKEND_DIR)

try:
    from backend.database import SessionLocal
    from backend.models import Player, ProviderIdMap
    from backend.services.fpl import PROVIDER, get_bootstrap_static
except ImportError:  # pragma: no cover
    from database import SessionLocal  # type: ignore
    from models import Player, ProviderIdMap  # type: ignore
    from services.fpl import PROVIDER, get_bootstrap_static  # type: ignore

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")
logger = logging.getLogger("sync_pl_fpl_player_stats")


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


def _fpl_photo_url(element: Dict[str, Any]) -> Optional[str]:
    """Build the public Premier League photo URL for an FPL element.

    FPL's `photo` field is a string like "12345.jpg" referencing an asset
    on `resources.premierleague.com`. The actual file is a PNG with the
    `p` prefix and a sized subfolder. We pick 250x250 (sharp on the EA-FC
    card, still light on bandwidth for list views).

    Returns None if the element has no photo asset.
    """
    raw = element.get("photo")
    if not raw or not isinstance(raw, str):
        return None
    # raw is e.g. "12345.jpg" -> strip the extension and rebuild as PNG.
    stem = raw.split(".", 1)[0]
    if not stem:
        return None
    return f"https://resources.premierleague.com/premierleague/photos/players/250x250/p{stem}.png"


def _apply_stats(player: Player, element: Dict[str, Any]) -> bool:
    """Apply both raw stats and FPL signal fields to a Player row."""
    new_values: Dict[str, Any] = {
        "goals_season": _to_int(element.get("goals_scored")),
        "assists_season": _to_int(element.get("assists")),
        "minutes_played": _to_int(element.get("minutes")),
        "fpl_total_points": _to_int(element.get("total_points")),
        "fpl_points_per_game": _to_float(element.get("points_per_game")),
        "fpl_form": _to_float(element.get("form")),
        "fpl_ict_index": _to_float(element.get("ict_index")),
        "fpl_influence": _to_float(element.get("influence")),
        "fpl_creativity": _to_float(element.get("creativity")),
        "fpl_threat": _to_float(element.get("threat")),
        "fpl_element_type": _to_int(element.get("element_type")),
    }

    # Photo is set only if the player doesn't already have one *or* the
    # element points to a different photo. Once set we don't overwrite a
    # populated url with None (a rotated player can drop their FPL photo
    # mid-season; we keep the last good one).
    fpl_photo = _fpl_photo_url(element)

    changed = False
    for attr, value in new_values.items():
        if value is None:
            continue
        if getattr(player, attr) != value:
            setattr(player, attr, value)
            changed = True

    if fpl_photo and player.photo_url != fpl_photo:
        player.photo_url = fpl_photo
        changed = True

    return changed


def main() -> int:
    parser = argparse.ArgumentParser(description="Sync PL player season stats from FPL.")
    parser.add_argument(
        "--mark-confidence-floor",
        type=int,
        default=0,
        help="Only update players whose FPL mapping confidence is >= this value (default: 0).",
    )
    args = parser.parse_args()

    floor = max(0, int(args.mark_confidence_floor))
    logger.info("Confidence floor: %d", floor)

    db = SessionLocal()
    counters = {"updated": 0, "skipped": 0, "missing": 0}
    network_calls = 0

    try:
        try:
            bootstrap = get_bootstrap_static(force_refresh=True)
            network_calls += 1
        except Exception as exc:  # noqa: BLE001
            logger.exception("FPL bootstrap-static fetch failed: %s", exc)
            return 1

        elements = bootstrap.get("elements") or []
        logger.info("Pulled %d FPL elements.", len(elements))

        # Pre-load all FPL player mappings so we don't hit the DB once per element.
        mapping_rows = (
            db.query(ProviderIdMap)
            .filter(
                ProviderIdMap.provider == PROVIDER,
                ProviderIdMap.entity_type == "player",
            )
            .all()
        )
        external_to_local: Dict[int, int] = {}
        external_to_confidence: Dict[int, float] = {}
        for row in mapping_rows:
            external_to_local[int(row.external_id)] = int(row.local_id)
            external_to_confidence[int(row.external_id)] = float(row.confidence) if row.confidence is not None else 0.0

        for element in elements:
            external_id = element.get("id")
            if external_id is None:
                counters["missing"] += 1
                continue

            local_id = external_to_local.get(int(external_id))
            if local_id is None:
                counters["missing"] += 1
                continue

            if external_to_confidence.get(int(external_id), 0.0) < floor:
                counters["skipped"] += 1
                continue

            player = db.query(Player).filter(Player.id == local_id).first()
            if player is None:
                counters["missing"] += 1
                continue

            if _apply_stats(player, element):
                counters["updated"] += 1
            else:
                counters["skipped"] += 1

        db.commit()

        print("\nFPL player stats sync summary")
        print("=" * 50)
        print(f"updated:        {counters['updated']}")
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
