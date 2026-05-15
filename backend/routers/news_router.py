"""News router exposing AI-generated articles to the frontend."""

from __future__ import annotations

import datetime
from typing import List, Optional

from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import BaseModel, Field
from sqlalchemy.orm import Session

try:
    from backend.database import get_db
    from backend.models import League, Match, NewsArticle, Team
except ImportError:
    from database import get_db  # type: ignore[no-redef]
    from models import League, Match, NewsArticle, Team  # type: ignore[no-redef]


router = APIRouter(prefix="/api/v1/editorial", tags=["news"])


# ---------------------------------------------------------------------------
# Schemas
# ---------------------------------------------------------------------------


class NewsTeamRef(BaseModel):
    id: int
    name: str
    logo_url: Optional[str] = None

    class Config:
        from_attributes = True


class NewsLeagueRef(BaseModel):
    id: int
    name: str
    country: Optional[str] = None

    class Config:
        from_attributes = True


class NewsArticleSummary(BaseModel):
    """Slim payload for the scrolling ticker bar."""

    id: int
    title: str
    summary: str
    news_type: str
    related_fixture_id: Optional[int] = None
    created_at: datetime.datetime


class NewsArticleFull(NewsArticleSummary):
    """Full payload for the sidebar / article page."""

    content: str
    league: Optional[NewsLeagueRef] = None
    home_team: Optional[NewsTeamRef] = None
    away_team: Optional[NewsTeamRef] = None


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _to_full(article: NewsArticle, db: Session) -> NewsArticleFull:
    league = (
        db.query(League).filter(League.id == article.league_id).one_or_none()
        if article.league_id
        else None
    )
    home = (
        db.query(Team).filter(Team.id == article.home_team_id).one_or_none()
        if article.home_team_id
        else None
    )
    away = (
        db.query(Team).filter(Team.id == article.away_team_id).one_or_none()
        if article.away_team_id
        else None
    )

    return NewsArticleFull(
        id=article.id,
        title=article.title,
        summary=article.summary,
        content=article.content,
        news_type=article.news_type,
        related_fixture_id=article.related_fixture_id,
        created_at=article.created_at,
        league=NewsLeagueRef.model_validate(league) if league else None,
        home_team=NewsTeamRef.model_validate(home) if home else None,
        away_team=NewsTeamRef.model_validate(away) if away else None,
    )


# ---------------------------------------------------------------------------
# Endpoints
# ---------------------------------------------------------------------------


@router.get("", response_model=List[NewsArticleFull])
def list_news(
    limit: int = Query(20, ge=1, le=100),
    news_type: Optional[str] = Query(None, pattern="^(post_match|pre_derby)$"),
    league_id: Optional[int] = Query(None),
    db: Session = Depends(get_db),
):
    """Return the most recent published articles."""
    q = db.query(NewsArticle).filter(NewsArticle.is_published.is_(True))
    if news_type:
        q = q.filter(NewsArticle.news_type == news_type)
    if league_id:
        q = q.filter(NewsArticle.league_id == league_id)
    rows = q.order_by(NewsArticle.created_at.desc()).limit(limit).all()
    return [_to_full(r, db) for r in rows]


@router.get("/feed", response_model=List[NewsArticleSummary])
def news_feed(
    limit: int = Query(15, ge=1, le=50),
    db: Session = Depends(get_db),
):
    """Slim feed for the top-of-page scrolling bar."""
    rows = (
        db.query(NewsArticle)
        .filter(NewsArticle.is_published.is_(True))
        .order_by(NewsArticle.created_at.desc())
        .limit(limit)
        .all()
    )
    return [
        NewsArticleSummary(
            id=r.id,
            title=r.title,
            summary=r.summary,
            news_type=r.news_type,
            related_fixture_id=r.related_fixture_id,
            created_at=r.created_at,
        )
        for r in rows
    ]


@router.get("/{article_id}", response_model=NewsArticleFull)
def get_news(article_id: int, db: Session = Depends(get_db)):
    article = db.query(NewsArticle).filter(NewsArticle.id == article_id).one_or_none()
    if not article or not article.is_published:
        raise HTTPException(status_code=404, detail="Article not found")
    return _to_full(article, db)
