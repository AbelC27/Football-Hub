"""
Generate custom news articles via Gemini and persist them to the database.

Usage:
    cd backend
    .venv/bin/python -m scripts.generate_custom_news
"""

import sys
import logging

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(message)s",
    handlers=[logging.StreamHandler(sys.stdout)],
)
logger = logging.getLogger(__name__)

try:
    from backend.database import SessionLocal
    from backend.models import NewsArticle, League, Team
    from backend.services.ai_news_agent import _call_gemini
except ImportError:
    from database import SessionLocal
    from models import NewsArticle, League, Team
    from services.ai_news_agent import _call_gemini


# ---------------------------------------------------------------------------
# Define the stories to generate
# ---------------------------------------------------------------------------

STORIES = [
    {
        "dedupe_key": "custom:arsenal_pl_champions_2025",
        "news_type": "editorial",
        "league_name": "Premier League",
        "prompt": (
            "Write a celebratory news article about Arsenal winning the 2024/25 "
            "Premier League title. This is their first league title since 2003/04 "
            "(the Invincibles season). Mikel Arteta has finally delivered the "
            "championship after years of rebuilding. Mention the significance of "
            "ending a 21-year wait, the role of key players like Saka, Saliba, "
            "Rice, and Ødegaard, and the emotional scenes at the Emirates. "
            "Keep it factual and celebratory in tone."
        ),
    },
    {
        "dedupe_key": "custom:west_ham_relegated_2025",
        "news_type": "editorial",
        "league_name": "Premier League",
        "prompt": (
            "Write a news article about West Ham United being relegated from the "
            "Premier League at the end of the 2024/25 season. This is a shocking "
            "fall for a club that won the Europa Conference League just two seasons "
            "ago. Mention the managerial instability, poor recruitment decisions, "
            "and the fans' frustration. The club will play in the Championship "
            "next season. Keep the tone serious and analytical, not mocking."
        ),
    },
]


def main():
    db = SessionLocal()
    try:
        for story in STORIES:
            dedupe_key = story["dedupe_key"]

            # Check if already exists
            existing = (
                db.query(NewsArticle)
                .filter(NewsArticle.dedupe_key == dedupe_key)
                .one_or_none()
            )
            if existing:
                logger.info("Article '%s' already exists (id=%d). Skipping.", dedupe_key, existing.id)
                continue

            # Find league
            league = (
                db.query(League)
                .filter(League.name == story["league_name"])
                .first()
            )

            logger.info("Generating article: %s ...", dedupe_key)
            try:
                payload = _call_gemini(story["prompt"])
            except Exception as exc:
                logger.error("Gemini call failed for '%s': %s", dedupe_key, exc)
                continue

            logger.info("  -> Title: %s", payload["title"])

            article = NewsArticle(
                title=payload["title"],
                summary=payload["summary"],
                content=payload["content"],
                news_type=story["news_type"],
                related_fixture_id=None,
                league_id=league.id if league else None,
                home_team_id=None,
                away_team_id=None,
                model_name="gemini-2.5-flash",
                dedupe_key=dedupe_key,
                is_published=True,
            )
            db.add(article)
            db.commit()
            logger.info("  -> Saved with id=%d", article.id)

        logger.info("Done.")
    finally:
        db.close()


if __name__ == "__main__":
    main()
