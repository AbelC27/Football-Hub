"""Lightweight client for api-sports.io (api-football v3).

This module is intentionally self-contained. It is *not* a replacement for
``backend/services/data_ingestion.py`` (which is left untouched). Instead we
provide:

* A single ``_get`` entrypoint that is rate-aware and quota-aware.
* Small focused helpers for the endpoints we actually consume.
* A custom ``ApisportsQuotaExceeded`` exception that callers can catch and
  surface as ``503`` to the UI without leaking provider details.

Quota strategy
--------------
api-sports.io free tier allows 100 calls / day (UTC). We track a per-process
counter that resets at UTC midnight and refuse to make a request once the
counter reaches ``MAX_DAILY_CALLS`` (defaults to 95, leaving a small headroom
for concurrent processes).
"""

from __future__ import annotations

import datetime as _dt
import logging
import os
import threading
from typing import Any, Dict, List, Optional

import requests
from dotenv import load_dotenv

load_dotenv()

logger = logging.getLogger(__name__)

API_KEY: Optional[str] = os.getenv("API_FOOTBALL_KEY")
BASE_URL = "https://v3.football.api-sports.io"

# Premier League is league 39 in api-sports.
PREMIER_LEAGUE_APISPORTS_ID = 39

# Hard ceiling we never want to cross. The free tier is 100/day; we keep a
# little headroom so two processes running side-by-side don't both go right
# up to the limit.
MAX_DAILY_CALLS = 95


class ApisportsQuotaExceeded(Exception):
    """Raised when we refuse to make a request because the local counter
    indicates we've hit the daily quota guardrail."""


class _CallCounter:
    """Process-local call counter with UTC-day rollover.

    Not perfect across multiple processes, but we don't need perfect: the
    api-sports response itself will eventually 429 us if we slip past the
    guardrail. This counter is mainly to *avoid* hitting the API when we
    already know we're at the limit.
    """

    def __init__(self) -> None:
        self._lock = threading.Lock()
        self._day = _dt.datetime.utcnow().date()
        self._count = 0

    def _maybe_rollover(self) -> None:
        today = _dt.datetime.utcnow().date()
        if today != self._day:
            logger.info(
                "apisports: day rollover %s -> %s, resetting call counter (was %d)",
                self._day,
                today,
                self._count,
            )
            self._day = today
            self._count = 0

    def check_and_increment(self) -> int:
        with self._lock:
            self._maybe_rollover()
            if self._count >= MAX_DAILY_CALLS:
                raise ApisportsQuotaExceeded(
                    f"Local quota guard tripped: already used {self._count} "
                    f"calls today (limit {MAX_DAILY_CALLS})."
                )
            self._count += 1
            return self._count

    @property
    def used_today(self) -> int:
        with self._lock:
            self._maybe_rollover()
            return self._count


_counter = _CallCounter()


def calls_used_today() -> int:
    """Returns the per-process count of api-sports calls used today (UTC)."""
    return _counter.used_today


def current_pl_season() -> int:
    """Return the season year for the Premier League.

    api-sports represents a season by its starting year, e.g. ``2024`` means
    the 2024/25 season. PL kicks off in August, so we flip on month >= 8.
    """
    today = _dt.date.today()
    return today.year if today.month >= 8 else today.year - 1


def _headers() -> Dict[str, str]:
    if not API_KEY:
        # Don't crash at import time; let the first call raise so the caller
        # can decide how to surface the misconfiguration.
        logger.warning("API_FOOTBALL_KEY is not set in the environment.")
    return {"x-apisports-key": API_KEY or ""}


def _get(path: str, params: Optional[Dict[str, Any]] = None, timeout: int = 15) -> Dict[str, Any]:
    """Issue a GET against api-sports.io with our standard headers.

    Raises:
        ApisportsQuotaExceeded: when the local counter is at the guardrail.
        requests.HTTPError: on non-2xx HTTP responses.
    """

    url = f"{BASE_URL}{path}"
    used = _counter.check_and_increment()
    logger.info("apisports GET %s params=%s (#%d today)", path, params or {}, used)

    response = requests.get(url, headers=_headers(), params=params or {}, timeout=timeout)
    if response.status_code == 429:
        # Force the local counter to the cap so subsequent calls bail fast.
        logger.warning("apisports returned 429 Too Many Requests; tripping quota guard.")
        raise ApisportsQuotaExceeded("Provider returned 429 Too Many Requests.")
    response.raise_for_status()

    payload = response.json()
    errors = payload.get("errors")
    if isinstance(errors, dict) and errors:
        # api-sports embeds an errors object with strings like
        # {"requests": "You have reached the request limit for the day"}.
        joined = "; ".join(f"{k}: {v}" for k, v in errors.items())
        if "limit" in joined.lower() or "quota" in joined.lower():
            raise ApisportsQuotaExceeded(joined)
        logger.warning("apisports response carried errors: %s", joined)

    return payload


# ---------------------------------------------------------------------------
# Helpers (each docstring states how many api calls it consumes).
# ---------------------------------------------------------------------------


def get_pl_teams(season: int) -> List[Dict[str, Any]]:
    """List Premier League teams for ``season``.

    API calls: 1.
    """
    payload = _get(
        "/teams",
        params={"league": PREMIER_LEAGUE_APISPORTS_ID, "season": season},
    )
    return payload.get("response", []) or []


def get_team_squad(team_id: int) -> List[Dict[str, Any]]:
    """Return the current squad list for ``team_id`` (api-sports id).

    API calls: 1. Returns ``response[0].players`` if present, else ``[]``.
    """
    payload = _get("/players/squads", params={"team": team_id})
    response = payload.get("response", []) or []
    if not response:
        return []
    first = response[0] or {}
    return first.get("players", []) or []


def get_topscorers(season: int) -> List[Dict[str, Any]]:
    """Top goal scorers for the Premier League. API calls: 1."""
    payload = _get(
        "/players/topscorers",
        params={"league": PREMIER_LEAGUE_APISPORTS_ID, "season": season},
    )
    return payload.get("response", []) or []


def get_topassists(season: int) -> List[Dict[str, Any]]:
    """Top assist providers for the Premier League. API calls: 1."""
    payload = _get(
        "/players/topassists",
        params={"league": PREMIER_LEAGUE_APISPORTS_ID, "season": season},
    )
    return payload.get("response", []) or []


def get_fixture_events(fixture_id: int) -> List[Dict[str, Any]]:
    """Events (goals, cards, subs) for an api-sports fixture id.

    API calls: 1.
    """
    payload = _get("/fixtures/events", params={"fixture": fixture_id})
    return payload.get("response", []) or []


def get_fixtures_by_date(
    season: int,
    date_iso: str,
    team_apisports_id: Optional[int] = None,
) -> List[Dict[str, Any]]:
    """Fetch PL fixtures for a single ``YYYY-MM-DD`` day.

    If ``team_apisports_id`` is supplied we narrow the search to fixtures
    involving that team (cuts down on responses to scan).

    API calls: 1.
    """
    params: Dict[str, Any] = {
        "league": PREMIER_LEAGUE_APISPORTS_ID,
        "season": season,
        "date": date_iso,
    }
    if team_apisports_id is not None:
        params["team"] = team_apisports_id

    payload = _get("/fixtures", params=params)
    return payload.get("response", []) or []


# ---------------------------------------------------------------------------
# World Cup helpers
# ---------------------------------------------------------------------------

WC_APISPORTS_LEAGUE_ID = 1  # FIFA World Cup in api-sports


def get_wc_fixtures_by_date(date_iso: str) -> List[Dict[str, Any]]:
    """Fetch WC fixtures for a date (YYYY-MM-DD). API calls: 1."""
    payload = _get("/fixtures", params={
        "league": WC_APISPORTS_LEAGUE_ID,
        "season": 2026,
        "date": date_iso,
    })
    return payload.get("response", []) or []


def get_fixture_statistics(fixture_id: int) -> List[Dict[str, Any]]:
    """Fetch team statistics for a fixture. API calls: 1."""
    payload = _get("/fixtures/statistics", params={"fixture": fixture_id})
    return payload.get("response", []) or []
