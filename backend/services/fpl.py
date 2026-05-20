"""Lightweight client for the public Fantasy Premier League JSON API.

This module is intentionally self-contained and mirrors the style of
``backend/services/apisports.py``, but FPL is keyless and does not enforce a
hard daily quota, so we only do polite rate limiting (a minimum 0.4s spacing
between consecutive HTTP calls) and a small in-memory TTL cache for the
``bootstrap-static`` payload (which is ~1MB and rarely changes).

Endpoints used (the FPL website itself uses these — there is no public docs
page, the shapes below are observed on the wire):

* ``GET /bootstrap-static/`` — single JSON document with ``events`` (the 38
  gameweeks), ``teams`` (the 20 PL clubs), ``elements`` (every player), plus
  ``element_types`` and ``phases``. Each element carries season-level
  aggregates: ``goals_scored``, ``assists``, ``minutes``, ``yellow_cards``,
  ``red_cards``, ``clean_sheets``, ``bonus``, ``total_points`` etc.

* ``GET /fixtures/`` — array of every PL fixture this season. Per-fixture
  fields used here: ``id`` (FPL fixture id), ``event`` (gameweek 1..38 or
  ``None`` for unscheduled), ``kickoff_time`` (ISO 8601), ``team_h``,
  ``team_a`` (FPL team ids), ``team_h_score``, ``team_a_score``,
  ``finished`` (bool). The ``stats`` array holds aggregated event blocks of
  shape ``{identifier, h: [{element, value}, ...], a: [...]}``. We consume
  the identifiers ``goals_scored``, ``assists``, ``yellow_cards``,
  ``red_cards``. There is no minute-by-minute timing — only counts per
  player per fixture.

* ``GET /fixtures/?event=N`` — same shape, filtered to a single gameweek.

There is also a ``persist_fpl_events_for_match(db, match) -> int`` helper
near the bottom of this module which is shared by the lazy-fallback in the
``/match/{id}/events`` route and by ``scripts/sync_pl_fpl_match_events.py``
so both paths produce identical ``MatchEvent`` rows.
"""

from __future__ import annotations

import datetime as _dt
import logging
import threading
import time
from typing import Any, Dict, List, Optional, Tuple

import requests

logger = logging.getLogger(__name__)

BASE_URL = "https://fantasy.premierleague.com/api"

PROVIDER = "fpl"
PL_LOCAL_LEAGUE_ID = 2021       # football-data.org id used as our local id
# FPL doesn't expose a competition id in the bootstrap response — the API is
# implicitly scoped to the Premier League. We persist ``1`` as the external
# id for the league mapping so the row remains a valid integer FK target,
# but the value is opaque (FPL does not surface a competition id anywhere).
PL_FPL_LEAGUE_ID = 1

# Per-call spacing. The FPL API doesn't publish a rate limit, but we want to
# be polite — the same domain serves the consumer-facing site.
_MIN_SECONDS_BETWEEN_CALLS = 0.4

# How long the bootstrap-static cache stays warm.
_BOOTSTRAP_CACHE_TTL_SECONDS = 5 * 60

_USER_AGENT = "TerraBall/1.0 (+contact@example.com)"


class _BootstrapCache:
    """Tiny TTL cache for the ~1MB bootstrap-static document."""

    def __init__(self, ttl_seconds: float) -> None:
        self._ttl = ttl_seconds
        self._payload: Optional[Dict[str, Any]] = None
        self._fetched_at: float = 0.0
        self._lock = threading.Lock()

    def get(self) -> Optional[Dict[str, Any]]:
        with self._lock:
            if self._payload is None:
                return None
            if (time.monotonic() - self._fetched_at) > self._ttl:
                return None
            return self._payload

    def set(self, payload: Dict[str, Any]) -> None:
        with self._lock:
            self._payload = payload
            self._fetched_at = time.monotonic()


_bootstrap_cache = _BootstrapCache(_BOOTSTRAP_CACHE_TTL_SECONDS)


# Spacing-guard state. Single shared lock for both _last_call_at and the
# cache writes so multi-threaded callers cannot stampede the upstream.
_call_lock = threading.Lock()
_last_call_at: float = 0.0


def _headers() -> Dict[str, str]:
    return {
        "User-Agent": _USER_AGENT,
        "Accept": "application/json",
    }


def _wait_for_spacing() -> None:
    """Block until at least ``_MIN_SECONDS_BETWEEN_CALLS`` has elapsed since
    the previous ``_get`` call. Thread-safe."""
    global _last_call_at
    with _call_lock:
        now = time.monotonic()
        delta = now - _last_call_at
        if delta < _MIN_SECONDS_BETWEEN_CALLS:
            sleep_for = _MIN_SECONDS_BETWEEN_CALLS - delta
        else:
            sleep_for = 0.0

    if sleep_for > 0:
        time.sleep(sleep_for)

    with _call_lock:
        _last_call_at = time.monotonic()


def _get(path: str, params: Optional[Dict[str, Any]] = None, timeout: int = 15) -> Any:
    """Issue a GET against the FPL API.

    Logs every call. Honors a polite minimum spacing between consecutive
    calls. Raises ``requests.HTTPError`` on non-2xx responses.
    """
    _wait_for_spacing()
    url = f"{BASE_URL}{path}"
    logger.info("fpl GET %s params=%s", path, params or {})
    response = requests.get(url, headers=_headers(), params=params or {}, timeout=timeout)
    response.raise_for_status()
    return response.json()


# ---------------------------------------------------------------------------
# Public helpers
# ---------------------------------------------------------------------------


def current_pl_season() -> int:
    """Return the season year for the Premier League (matches
    ``apisports.current_pl_season``). PL flips on month >= 8."""
    today = _dt.date.today()
    return today.year if today.month >= 8 else today.year - 1


def get_bootstrap_static(force_refresh: bool = False) -> Dict[str, Any]:
    """Return the parsed ``bootstrap-static`` JSON.

    Cached for ``_BOOTSTRAP_CACHE_TTL_SECONDS`` (default 5 minutes) since the
    payload is large and rarely changes. Pass ``force_refresh=True`` to
    bypass the cache.
    """
    if not force_refresh:
        cached = _bootstrap_cache.get()
        if cached is not None:
            return cached

    payload = _get("/bootstrap-static/")
    if not isinstance(payload, dict):
        raise ValueError("Unexpected bootstrap-static payload shape (not a dict).")
    _bootstrap_cache.set(payload)
    return payload


def get_all_fixtures() -> List[Dict[str, Any]]:
    """Return every PL fixture for the current season. No cache."""
    payload = _get("/fixtures/")
    if not isinstance(payload, list):
        raise ValueError("Unexpected fixtures payload shape (not a list).")
    return payload


def get_gameweek_fixtures(event: int) -> List[Dict[str, Any]]:
    """Return PL fixtures for a single gameweek. No cache."""
    payload = _get("/fixtures/", params={"event": int(event)})
    if not isinstance(payload, list):
        raise ValueError("Unexpected fixtures payload shape (not a list).")
    return payload


# ---------------------------------------------------------------------------
# Shared helper: persist FPL events for a single local Match.
#
# This is used by both the lazy fallback in the ``/match/{id}/events`` route
# and by ``scripts/sync_pl_fpl_match_events.py``, so both produce identical
# rows. Imports are deferred to avoid pulling SQLAlchemy on module load.
# ---------------------------------------------------------------------------


_FPL_EVENT_NOTE = "fpl"  # written to MatchEvent.detail metadata where useful

# Detail strings used on emitted MatchEvent rows. Kept as module-level
# constants so the route, the script, and the refresh deletion logic stay in
# sync — these strings are how we recognise FPL-origin rows.
DETAIL_GOAL = "Normal Goal (FPL)"
DETAIL_ASSIST = "Assist (FPL)"
DETAIL_YELLOW_CARD = "Yellow Card"
DETAIL_RED_CARD = "Red Card"


def _kickoff_to_dt(kickoff_iso: Optional[str]) -> Optional[_dt.datetime]:
    if not kickoff_iso:
        return None
    try:
        # FPL uses ISO 8601 with trailing Z.
        return _dt.datetime.fromisoformat(kickoff_iso.replace("Z", "+00:00"))
    except ValueError:
        return None


def _resolve_fpl_fixture_for_match(
    db,
    match,
    fixtures: List[Dict[str, Any]],
    match_window_hours: int = 6,
) -> Tuple[Optional[Dict[str, Any]], Optional[int]]:
    """Locate the FPL fixture corresponding to a local Match row.

    Returns ``(fixture, fpl_fixture_id)`` or ``(None, None)`` if it cannot
    be resolved. If a fixture is resolved by team+kickoff window, the
    mapping is *not* persisted here — callers persist it themselves so they
    can decide how to handle commit/rollback.
    """
    try:
        from backend.models import ProviderIdMap
    except ImportError:  # pragma: no cover - script-style import fallback
        from models import ProviderIdMap  # type: ignore

    # 1. Exact mapping in ProviderIdMap.
    existing = (
        db.query(ProviderIdMap)
        .filter(
            ProviderIdMap.provider == PROVIDER,
            ProviderIdMap.entity_type == "match",
            ProviderIdMap.local_id == match.id,
        )
        .first()
    )
    if existing is not None:
        fpl_id = int(existing.external_id)
        for fx in fixtures:
            if int(fx.get("id") or -1) == fpl_id:
                return fx, fpl_id
        # Mapped but no longer present in the fetched list (shouldn't really
        # happen mid-season, but don't pretend it does).
        return None, fpl_id

    # 2. Resolve via team mapping + kickoff window.
    team_rows = (
        db.query(ProviderIdMap)
        .filter(
            ProviderIdMap.provider == PROVIDER,
            ProviderIdMap.entity_type == "team",
            ProviderIdMap.local_id.in_([match.home_team_id, match.away_team_id]),
        )
        .all()
    )
    local_to_fpl = {row.local_id: int(row.external_id) for row in team_rows}
    fpl_home = local_to_fpl.get(match.home_team_id)
    fpl_away = local_to_fpl.get(match.away_team_id)
    if fpl_home is None or fpl_away is None:
        return None, None
    if not match.start_time:
        return None, None

    target_dt = match.start_time
    if target_dt.tzinfo is None:
        target_dt = target_dt.replace(tzinfo=_dt.timezone.utc)

    window = _dt.timedelta(hours=int(match_window_hours))
    candidates: List[Dict[str, Any]] = []
    for fx in fixtures:
        if int(fx.get("team_h") or -1) != fpl_home:
            continue
        if int(fx.get("team_a") or -1) != fpl_away:
            continue
        kickoff_dt = _kickoff_to_dt(fx.get("kickoff_time"))
        if kickoff_dt is None:
            continue
        if abs(kickoff_dt - target_dt) <= window:
            candidates.append(fx)

    if len(candidates) != 1:
        return None, None
    fixture = candidates[0]
    return fixture, int(fixture.get("id"))


def _team_side_to_local_id(side: str, match) -> Optional[int]:
    if side == "h":
        return match.home_team_id
    if side == "a":
        return match.away_team_id
    return None


def _emit_match_events_from_stats(
    match,
    fixture: Dict[str, Any],
    fpl_player_to_local_player: Dict[int, int],
    fpl_player_id_to_name: Dict[int, str],
) -> List[Dict[str, Any]]:
    """Walk fixture['stats'] and produce MatchEvent kwargs dicts.

    No DB writes here — pure transformation so callers can choose how to
    persist (insert, refresh, etc).
    """
    rows: List[Dict[str, Any]] = []
    stats = fixture.get("stats") or []
    for block in stats:
        identifier = (block or {}).get("identifier")
        if identifier not in {"goals_scored", "assists", "yellow_cards", "red_cards"}:
            continue
        for side in ("h", "a"):
            local_team_id = _team_side_to_local_id(side, match)
            if local_team_id is None:
                continue
            for entry in (block.get(side) or []):
                fpl_player_id = entry.get("element")
                count = int(entry.get("value") or 0)
                if fpl_player_id is None or count <= 0:
                    continue
                fpl_player_id = int(fpl_player_id)
                local_player_id = fpl_player_to_local_player.get(fpl_player_id)
                fallback_name = fpl_player_id_to_name.get(fpl_player_id) or f"FPL element {fpl_player_id}"

                if identifier == "goals_scored":
                    event_type = "Goal"
                    detail = DETAIL_GOAL
                elif identifier == "assists":
                    event_type = "Assist"
                    detail = DETAIL_ASSIST
                elif identifier == "yellow_cards":
                    event_type = "Card"
                    detail = DETAIL_YELLOW_CARD
                else:  # red_cards
                    event_type = "Card"
                    detail = DETAIL_RED_CARD

                for _ in range(count):
                    rows.append(
                        {
                            "match_id": match.id,
                            # FPL doesn't carry minute-by-minute timing.
                            "minute": None,
                            "event_type": event_type,
                            "team_id": local_team_id,
                            "player_name": fallback_name,
                            "detail": detail,
                            "player_id": local_player_id,
                            # FPL doesn't pair scorers and assisters; the
                            # 'Assist' rows live as standalone events.
                            "assist_player_id": None,
                            "assist_player_name": None,
                        }
                    )
    return rows


def persist_fpl_events_for_match(db, match, *, refresh: bool = False) -> int:
    """Resolve the FPL fixture for ``match`` and persist its event rows.

    Returns the number of newly-inserted ``MatchEvent`` rows. If
    ``refresh`` is true, existing FPL-origin rows for this match are
    deleted first (heuristic: ``detail`` ends with ``(FPL)`` for goals and
    assists, or matches the cards we emit). Callers are responsible for
    committing — this function does its own commit on success and
    rolls back on errors.

    On any failure (FPL fetch error, no fixture resolved, no team
    mapping) returns ``0`` and leaves the DB clean.
    """
    try:
        from backend.models import MatchEvent, Player, ProviderIdMap
    except ImportError:  # pragma: no cover - script-style import fallback
        from models import MatchEvent, Player, ProviderIdMap  # type: ignore

    try:
        fixtures = get_all_fixtures()
    except Exception as exc:  # noqa: BLE001 - degraded data path
        logger.warning("FPL fixtures fetch failed for match %s: %s", getattr(match, "id", "?"), exc)
        return 0

    fixture, fpl_fixture_id = _resolve_fpl_fixture_for_match(db, match, fixtures)
    if fixture is None or fpl_fixture_id is None:
        logger.info(
            "FPL fallback: no fixture resolved for local match %s.",
            getattr(match, "id", "?"),
        )
        return 0

    if not fixture.get("finished"):
        logger.info(
            "FPL fallback: fixture %d (local match %s) is not finished yet; skipping.",
            fpl_fixture_id,
            getattr(match, "id", "?"),
        )
        return 0

    # Build FPL player id -> local player id map for the players that
    # actually appear in this fixture's stats.
    fpl_player_ids: List[int] = []
    fpl_player_id_to_name: Dict[int, str] = {}
    for block in fixture.get("stats") or []:
        for side in ("h", "a"):
            for entry in (block.get(side) or []):
                fpid = entry.get("element")
                if fpid is not None:
                    fpl_player_ids.append(int(fpid))

    fpl_player_to_local_player: Dict[int, int] = {}
    if fpl_player_ids:
        rows = (
            db.query(ProviderIdMap)
            .filter(
                ProviderIdMap.provider == PROVIDER,
                ProviderIdMap.entity_type == "player",
                ProviderIdMap.external_id.in_(list(set(fpl_player_ids))),
            )
            .all()
        )
        fpl_player_to_local_player = {int(r.external_id): int(r.local_id) for r in rows}

        # Best-effort: pull display names. Prefer the local Player.name when
        # we have a mapping; fall back to a placeholder otherwise.
        if fpl_player_to_local_player:
            local_ids = list(fpl_player_to_local_player.values())
            local_players = db.query(Player).filter(Player.id.in_(local_ids)).all()
            local_id_to_name = {p.id: p.name for p in local_players}
            for fpl_id, local_id in fpl_player_to_local_player.items():
                name = local_id_to_name.get(local_id)
                if name:
                    fpl_player_id_to_name[fpl_id] = name

    new_rows = _emit_match_events_from_stats(
        match,
        fixture,
        fpl_player_to_local_player,
        fpl_player_id_to_name,
    )

    try:
        if refresh:
            existing = (
                db.query(MatchEvent)
                .filter(MatchEvent.match_id == match.id)
                .all()
            )
            for row in existing:
                # Heuristic: the script/route only ever emits these exact
                # ``detail`` values for FPL-origin rows, and the api-sports
                # path does not use the ``(FPL)`` suffix. The card rows are
                # ambiguous, so we only nuke them when ``minute`` is None
                # (FPL never sets minutes).
                if row.detail in {DETAIL_GOAL, DETAIL_ASSIST}:
                    db.delete(row)
                elif row.detail in {DETAIL_YELLOW_CARD, DETAIL_RED_CARD} and row.minute is None:
                    db.delete(row)
            db.flush()

        # Persist the match-id mapping if it isn't already there. We do
        # this regardless of how the fixture was resolved, so subsequent
        # calls don't pay a fresh fixtures fetch traversal.
        existing_map = (
            db.query(ProviderIdMap)
            .filter(
                ProviderIdMap.provider == PROVIDER,
                ProviderIdMap.entity_type == "match",
                ProviderIdMap.local_id == match.id,
            )
            .first()
        )
        if existing_map is None:
            db.add(
                ProviderIdMap(
                    provider=PROVIDER,
                    entity_type="match",
                    local_id=match.id,
                    external_id=int(fpl_fixture_id),
                    confidence=100.0,
                    notes="resolved via team+kickoff window",
                )
            )

        inserted = 0
        for kwargs in new_rows:
            db.add(MatchEvent(**kwargs))
            inserted += 1

        db.commit()
        return inserted
    except Exception as exc:  # noqa: BLE001 - degraded data path
        db.rollback()
        logger.exception(
            "FPL fallback: failed to persist events for match %s: %s",
            getattr(match, "id", "?"),
            exc,
        )
        return 0
