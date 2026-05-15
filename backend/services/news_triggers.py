"""Scheduler-callable triggers for the AI News Agent.

These functions are intended to be registered as APScheduler jobs.
They never raise; failures are logged so the scheduler keeps running.
"""

from __future__ import annotations

import datetime
import logging
from typing import Iterable

import pytz
from sqlalchemy.orm import Session

try:
    from backend.database import SessionLocal
    from backend.models import League, Match, NewsArticle, Team
    from backend.services.ai_news_agent import (
        AINewsAgentError,
        build_post_match_context,
        build_pre_derby_context,
        generate_post_match_article,
        generate_pre_derby_article,
        is_derby,
        persist_article,
    )
except ImportError:  # script-style execution
    from database import SessionLocal  # type: ignore[no-redef]
    from models import League, Match, NewsArticle, Team  # type: ignore[no-redef]
    from services.ai_news_agent import (  # type: ignore[no-redef]
        AINewsAgentError,
        build_post_match_context,
        build_pre_derby_context,
        generate_post_match_article,
        generate_pre_derby_article,
        is_derby,
        persist_article,
    )


logger = logging.getLogger(__name__)

FINISHED_STATUSES = {"FT", "AET", "PEN"}
UPCOMING_STATUSES = {"NS", "TBD"}
PRE_DERBY_WINDOW_HOURS = 24


# ---------------------------------------------------------------------------
# Post-match generator
# ---------------------------------------------------------------------------

def _existing_dedupe_keys(db: Session, keys: Iterable[str]) -> set[str]:
    keys = list(keys)
    if not keys:
        return set()
    rows = (
        db.query(NewsArticle.dedupe_key)
        .filter(NewsArticle.dedupe_key.in_(keys))
        .all()
    )
    return {r[0] for r in rows}


def run_post_match_news() -> None:
    """Scan recently-finished matches and generate one article per match."""
    db = SessionLocal()
    try:
        # Look at fixtures finished in the last 6 hours so we don't backfill the
        # entire historical season every startup.
        cutoff = datetime.datetime.now(tz=pytz.UTC) - datetime.timedelta(hours=6)
        finished = (
            db.query(Match)
            .filter(Match.status.in_(FINISHED_STATUSES))
            .filter(Match.start_time >= cutoff)
            .all()
        )

        if not finished:
            logger.debug("post_match_news: no recently finished matches")
            return

        keys = [f"post_match:{m.id}" for m in finished]
        already = _existing_dedupe_keys(db, keys)

        new_articles = 0
        for match in finished:
            key = f"post_match:{match.id}"
            if key in already:
                continue
            try:
                ctx = build_post_match_context(db, match)
                payload = generate_post_match_article(ctx)
                persist_article(
                    db,
                    payload,
                    fixture_id=match.id,
                    league_id=match.league_id,
                    home_team_id=match.home_team_id,
                    away_team_id=match.away_team_id,
                    news_type="post_match",
                    dedupe_key=key,
                )
                new_articles += 1
            except AINewsAgentError as exc:
                logger.warning("post_match_news: LLM error for match=%s: %s", match.id, exc)
            except Exception:
                db.rollback()
                logger.exception("post_match_news: unexpected error for match=%s", match.id)

        if new_articles:
            logger.info("post_match_news: generated %s new articles", new_articles)
    finally:
        db.close()


# ---------------------------------------------------------------------------
# Pre-derby generator
# ---------------------------------------------------------------------------

def run_pre_derby_news() -> None:
    """Find derby fixtures kicking off in < 24h and generate previews."""
    db = SessionLocal()
    try:
        now = datetime.datetime.now(tz=pytz.UTC)
        window_end = now + datetime.timedelta(hours=PRE_DERBY_WINDOW_HOURS)

        # Note: Match.start_time may be stored naive in some installs. We pass
        # the boundaries as datetimes; SQLAlchemy/Postgres will coerce.
        upcoming = (
            db.query(Match)
            .filter(Match.status.in_(UPCOMING_STATUSES))
            .filter(Match.start_time >= now.replace(tzinfo=None))
            .filter(Match.start_time <= window_end.replace(tzinfo=None))
            .all()
        )

        if not upcoming:
            logger.debug("pre_derby_news: no upcoming fixtures within %sh", PRE_DERBY_WINDOW_HOURS)
            return

        candidate_keys: list[str] = []
        candidates: list[tuple[Match, Team, Team, League | None, str]] = []

        for match in upcoming:
            home = db.query(Team).filter(Team.id == match.home_team_id).one_or_none()
            away = db.query(Team).filter(Team.id == match.away_team_id).one_or_none()
            if not home or not away:
                continue
            league = (
                db.query(League).filter(League.id == match.league_id).one_or_none()
                if match.league_id
                else None
            )
            ok, label = is_derby(home, away, league)
            if not ok:
                continue
            key = f"pre_derby:{match.id}"
            candidate_keys.append(key)
            candidates.append((match, home, away, league, label or "Derby"))

        if not candidates:
            return

        already = _existing_dedupe_keys(db, candidate_keys)

        new_articles = 0
        for match, _home, _away, _league, _label in candidates:
            key = f"pre_derby:{match.id}"
            if key in already:
                continue
            try:
                ctx = build_pre_derby_context(db, match)
                payload = generate_pre_derby_article(ctx)
                persist_article(
                    db,
                    payload,
                    fixture_id=match.id,
                    league_id=match.league_id,
                    home_team_id=match.home_team_id,
                    away_team_id=match.away_team_id,
                    news_type="pre_derby",
                    dedupe_key=key,
                )
                new_articles += 1
            except AINewsAgentError as exc:
                logger.warning("pre_derby_news: LLM error for match=%s: %s", match.id, exc)
            except Exception:
                db.rollback()
                logger.exception("pre_derby_news: unexpected error for match=%s", match.id)

        if new_articles:
            logger.info("pre_derby_news: generated %s new articles", new_articles)
    finally:
        db.close()
