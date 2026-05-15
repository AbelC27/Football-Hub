"""AI News Agent service.

Generates short, journalistic football news articles by calling the
OpenRouter API (https://openrouter.ai/) using a GPT-4-class model.

The service is provider-agnostic in spirit — OpenRouter exposes an
OpenAI-compatible chat-completions endpoint, so we use plain `httpx`
rather than pulling in the `openai` SDK.

Public entry points
-------------------
- `generate_post_match_article(fixture_ctx)`  -> dict | None
- `generate_pre_derby_article(fixture_ctx)`   -> dict | None
- `build_post_match_context(db, match)`       -> dict
- `build_pre_derby_context(db, match)`        -> dict
- `is_derby(home_team, away_team, league)`    -> bool
- `persist_article(db, payload, *, fixture_id, league_id, home_team_id, away_team_id, news_type, dedupe_key)`

The `*_context` helpers gather the data needed for prompting from the
existing SQLAlchemy models (Match, Team, League, MatchStatistics,
MatchEvent). The `generate_*` functions take that context dict, build
a prompt, hit OpenRouter, and return a structured payload
(`{title, summary, content}`) ready to be persisted.
"""

from __future__ import annotations

import json
import logging
import os
import re
from typing import Any, Dict, List, Optional, Tuple

import httpx
from sqlalchemy.orm import Session

try:
    from backend.models import (
        League,
        Match,
        MatchEvent,
        MatchStatistics,
        NewsArticle,
        Team,
    )
except ImportError:  # script-style execution
    from models import (  # type: ignore[no-redef]
        League,
        Match,
        MatchEvent,
        MatchStatistics,
        NewsArticle,
        Team,
    )


logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Config
# ---------------------------------------------------------------------------

OPENROUTER_API_URL = "https://openrouter.ai/api/v1/chat/completions"
OPENROUTER_API_KEY = os.getenv("OPENROUTER_API_KEY", "").strip()
OPENROUTER_MODEL = os.getenv("OPENROUTER_MODEL", "openai/gpt-4o").strip()

# Optional but recommended by OpenRouter for attribution
OPENROUTER_REFERER = os.getenv("OPENROUTER_REFERER", "http://localhost:3000")
OPENROUTER_APP_TITLE = os.getenv("OPENROUTER_APP_TITLE", "TerraBall")

REQUEST_TIMEOUT_SECONDS = 30.0

SYSTEM_PROMPT = """You are a senior football journalist writing for a modern
sports publication. You produce concise, factual, and engaging match coverage.

Style guide:
- Tone: professional, energetic, neutral. Never sensationalist.
- Always ground every claim in the supplied facts. Never invent stats,
  players, quotes, transfers, or events.
- Prefer active voice and concrete verbs. Avoid clichés such as
  "beautiful game", "foot-stomping action", or "the rest is history".
- British English spelling.
- Match-report leads should open with the headline result. Pre-match
  derby pieces should open with the stakes and the rivalry context.

Output format:
You MUST reply with a single JSON object and nothing else. No markdown
fences, no commentary. The schema is:
{
  "title":   "string, 60-110 characters",
  "summary": "string, one sentence, 140-220 characters, suitable for a
              scrolling news ticker",
  "content": "string, 180-320 words, plain prose with paragraph breaks
              represented by \\n\\n. No markdown headings."
}
"""


# ---------------------------------------------------------------------------
# Derby detection
# ---------------------------------------------------------------------------

# Curated list of well-known fixtures we tag as derbies. Keys are
# frozensets of normalised team names so order doesn't matter. Values
# are the editorial label used in the prompt.
KNOWN_DERBIES: Dict[frozenset, str] = {
    # Premier League
    frozenset({"manchester united", "manchester city"}): "Manchester Derby",
    frozenset({"manchester united", "liverpool"}): "North-West Derby",
    frozenset({"arsenal", "tottenham hotspur"}): "North London Derby",
    frozenset({"arsenal", "tottenham"}): "North London Derby",
    frozenset({"chelsea", "arsenal"}): "London Derby",
    frozenset({"chelsea", "tottenham hotspur"}): "London Derby",
    frozenset({"chelsea", "tottenham"}): "London Derby",
    frozenset({"everton", "liverpool"}): "Merseyside Derby",
    # La Liga
    frozenset({"real madrid", "barcelona"}): "El Clásico",
    frozenset({"fc barcelona", "real madrid"}): "El Clásico",
    frozenset({"real madrid", "atletico madrid"}): "Madrid Derby",
    frozenset({"real madrid", "atlético madrid"}): "Madrid Derby",
    frozenset({"sevilla", "real betis"}): "Seville Derby",
    # Serie A
    frozenset({"inter", "ac milan"}): "Derby della Madonnina",
    frozenset({"internazionale", "ac milan"}): "Derby della Madonnina",
    frozenset({"inter milan", "ac milan"}): "Derby della Madonnina",
    frozenset({"juventus", "inter"}): "Derby d'Italia",
    frozenset({"juventus", "internazionale"}): "Derby d'Italia",
    frozenset({"roma", "lazio"}): "Derby della Capitale",
    frozenset({"as roma", "lazio"}): "Derby della Capitale",
    frozenset({"napoli", "roma"}): "Derby del Sole",
    # Bundesliga
    frozenset({"bayern munich", "borussia dortmund"}): "Der Klassiker",
    frozenset({"fc bayern münchen", "borussia dortmund"}): "Der Klassiker",
    frozenset({"borussia dortmund", "schalke 04"}): "Revierderby",
    # Ligue 1
    frozenset({"paris saint-germain", "marseille"}): "Le Classique",
    frozenset({"psg", "marseille"}): "Le Classique",
    frozenset({"paris saint-germain", "olympique de marseille"}): "Le Classique",
}


def _norm(name: Optional[str]) -> str:
    if not name:
        return ""
    return re.sub(r"\s+", " ", name).strip().lower()


def is_derby(
    home_team: Optional[Team],
    away_team: Optional[Team],
    league: Optional[League] = None,  # noqa: ARG001 — reserved for future heuristics
) -> Tuple[bool, Optional[str]]:
    """Return (is_derby, label) for the given pair of teams."""
    if not home_team or not away_team:
        return False, None
    key = frozenset({_norm(home_team.name), _norm(away_team.name)})
    label = KNOWN_DERBIES.get(key)
    return label is not None, label


# ---------------------------------------------------------------------------
# Context builders
# ---------------------------------------------------------------------------

def _events_summary(db: Session, match_id: int) -> List[Dict[str, Any]]:
    rows = (
        db.query(MatchEvent)
        .filter(MatchEvent.match_id == match_id)
        .order_by(MatchEvent.minute.asc().nullsfirst())
        .all()
    )
    return [
        {
            "minute": ev.minute,
            "type": ev.event_type,
            "team_id": ev.team_id,
            "player": ev.player_name,
            "detail": ev.detail,
        }
        for ev in rows
    ]


def _stats_summary(db: Session, match_id: int) -> Optional[Dict[str, Any]]:
    stats = (
        db.query(MatchStatistics)
        .filter(MatchStatistics.match_id == match_id)
        .one_or_none()
    )
    if not stats:
        return None
    # Be defensive: not every column may exist on every deployed schema.
    fields = (
        "possession_home",
        "possession_away",
        "shots_on_home",
        "shots_on_away",
        "shots_total_home",
        "shots_total_away",
        "corners_home",
        "corners_away",
        "fouls_home",
        "fouls_away",
    )
    out: Dict[str, Any] = {}
    for f in fields:
        if hasattr(stats, f):
            out[f] = getattr(stats, f)
    return out


def build_post_match_context(db: Session, match: Match) -> Dict[str, Any]:
    home = db.query(Team).filter(Team.id == match.home_team_id).one_or_none()
    away = db.query(Team).filter(Team.id == match.away_team_id).one_or_none()
    league = (
        db.query(League).filter(League.id == match.league_id).one_or_none()
        if match.league_id
        else None
    )

    return {
        "match_id": match.id,
        "kickoff": match.start_time.isoformat() if match.start_time else None,
        "status": match.status,
        "home": {
            "id": home.id if home else None,
            "name": home.name if home else "Home team",
            "stadium": home.stadium if home else None,
        },
        "away": {
            "id": away.id if away else None,
            "name": away.name if away else "Away team",
        },
        "score": {"home": match.home_score, "away": match.away_score},
        "league": {
            "id": league.id if league else None,
            "name": league.name if league else None,
            "country": league.country if league else None,
        },
        "events": _events_summary(db, match.id),
        "stats": _stats_summary(db, match.id),
    }


def build_pre_derby_context(db: Session, match: Match) -> Dict[str, Any]:
    home = db.query(Team).filter(Team.id == match.home_team_id).one_or_none()
    away = db.query(Team).filter(Team.id == match.away_team_id).one_or_none()
    league = (
        db.query(League).filter(League.id == match.league_id).one_or_none()
        if match.league_id
        else None
    )
    _, derby_label = is_derby(home, away, league)
    return {
        "match_id": match.id,
        "kickoff": match.start_time.isoformat() if match.start_time else None,
        "derby_label": derby_label,
        "home": {
            "id": home.id if home else None,
            "name": home.name if home else "Home team",
            "stadium": home.stadium if home else None,
        },
        "away": {
            "id": away.id if away else None,
            "name": away.name if away else "Away team",
        },
        "league": {
            "id": league.id if league else None,
            "name": league.name if league else None,
            "country": league.country if league else None,
        },
    }


# ---------------------------------------------------------------------------
# OpenRouter call
# ---------------------------------------------------------------------------


class AINewsAgentError(RuntimeError):
    """Raised when the upstream LLM call fails or returns malformed output."""


def _call_openrouter(user_prompt: str) -> Dict[str, str]:
    if not OPENROUTER_API_KEY:
        raise AINewsAgentError(
            "OPENROUTER_API_KEY is not set. Add it to backend/.env to enable the news agent."
        )

    headers = {
        "Authorization": f"Bearer {OPENROUTER_API_KEY}",
        "Content-Type": "application/json",
        "HTTP-Referer": OPENROUTER_REFERER,
        "X-Title": OPENROUTER_APP_TITLE,
    }
    payload = {
        "model": OPENROUTER_MODEL,
        "temperature": 0.6,
        "max_tokens": 900,
        "response_format": {"type": "json_object"},
        "messages": [
            {"role": "system", "content": SYSTEM_PROMPT},
            {"role": "user", "content": user_prompt},
        ],
    }

    try:
        with httpx.Client(timeout=REQUEST_TIMEOUT_SECONDS) as client:
            resp = client.post(OPENROUTER_API_URL, headers=headers, json=payload)
    except httpx.HTTPError as exc:
        raise AINewsAgentError(f"OpenRouter HTTP error: {exc}") from exc

    if resp.status_code != 200:
        raise AINewsAgentError(
            f"OpenRouter returned {resp.status_code}: {resp.text[:500]}"
        )

    try:
        body = resp.json()
        raw = body["choices"][0]["message"]["content"]
    except (KeyError, ValueError, IndexError) as exc:
        raise AINewsAgentError(f"Malformed OpenRouter response: {exc}") from exc

    parsed = _safe_json_loads(raw)
    if not parsed:
        raise AINewsAgentError(f"LLM did not return valid JSON. Got: {raw[:300]}")

    title = (parsed.get("title") or "").strip()
    summary = (parsed.get("summary") or "").strip()
    content = (parsed.get("content") or "").strip()
    if not (title and summary and content):
        raise AINewsAgentError(
            f"LLM JSON is missing required fields. Got keys: {list(parsed.keys())}"
        )

    # Hard length caps to fit the DB columns and the ticker UI.
    return {
        "title": title[:255],
        "summary": summary[:280],
        "content": content,
    }


def _safe_json_loads(raw: str) -> Optional[Dict[str, Any]]:
    """Parse JSON, tolerating accidental ```json fences."""
    s = raw.strip()
    if s.startswith("```"):
        s = re.sub(r"^```(?:json)?\s*", "", s)
        s = re.sub(r"\s*```$", "", s)
    try:
        return json.loads(s)
    except json.JSONDecodeError:
        # Last resort: extract the first {...} block
        match = re.search(r"\{.*\}", s, re.DOTALL)
        if match:
            try:
                return json.loads(match.group(0))
            except json.JSONDecodeError:
                return None
        return None


# ---------------------------------------------------------------------------
# Generation
# ---------------------------------------------------------------------------

def generate_post_match_article(ctx: Dict[str, Any]) -> Dict[str, str]:
    """Generate a post-match report. Returns {title, summary, content}."""
    prompt = (
        "Write a post-match news report for the following fixture. "
        "Use only the facts provided.\n\n"
        f"FIXTURE_FACTS:\n{json.dumps(ctx, default=str, ensure_ascii=False)}"
    )
    return _call_openrouter(prompt)


def generate_pre_derby_article(ctx: Dict[str, Any]) -> Dict[str, str]:
    """Generate a pre-derby preview piece. Returns {title, summary, content}."""
    prompt = (
        "Write a pre-match preview for the upcoming derby fixture below. "
        "Set the scene, stress what's at stake, and reference the rivalry "
        "label provided. Use only the facts given; do not invent line-ups, "
        "quotes, or recent form figures.\n\n"
        f"FIXTURE_FACTS:\n{json.dumps(ctx, default=str, ensure_ascii=False)}"
    )
    return _call_openrouter(prompt)


# ---------------------------------------------------------------------------
# Persistence helper
# ---------------------------------------------------------------------------

def persist_article(
    db: Session,
    payload: Dict[str, str],
    *,
    fixture_id: Optional[int],
    league_id: Optional[int],
    home_team_id: Optional[int],
    away_team_id: Optional[int],
    news_type: str,
    dedupe_key: str,
) -> Optional[NewsArticle]:
    """Insert a NewsArticle row, ignoring duplicates by `dedupe_key`."""
    existing = (
        db.query(NewsArticle).filter(NewsArticle.dedupe_key == dedupe_key).one_or_none()
    )
    if existing:
        logger.debug("News article already exists for key=%s", dedupe_key)
        return existing

    article = NewsArticle(
        title=payload["title"],
        summary=payload["summary"],
        content=payload["content"],
        news_type=news_type,
        related_fixture_id=fixture_id,
        league_id=league_id,
        home_team_id=home_team_id,
        away_team_id=away_team_id,
        model_name=OPENROUTER_MODEL,
        dedupe_key=dedupe_key,
        is_published=True,
    )
    db.add(article)
    db.commit()
    db.refresh(article)
    return article
