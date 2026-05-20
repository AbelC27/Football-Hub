import sys
import os

# Ensure backend package can be imported
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from backend.database import SessionLocal
from backend.models import Match
from backend.services.ai_news_agent import (
    build_post_match_context,
    generate_post_match_article,
    persist_article,
)

def seed_news():
    db = SessionLocal()
    try:
        # Find 6 finished matches (status = 'FT')
        finished_matches = (
            db.query(Match)
            .filter(Match.status == "FT")
            .order_by(Match.start_time.desc())
            .limit(6)
            .all()
        )
        
        if not finished_matches:
            print("No finished matches found in the database. Cannot generate news.")
            return

        print(f"Found {len(finished_matches)} finished matches. Generating AI news...")
        
        count = 0
        for match in finished_matches:
            print(f"Generating news for Match ID: {match.id} (Home ID {match.home_team_id} vs Away ID {match.away_team_id})...")
            
            ctx = build_post_match_context(db, match)
            
            # Generate the article via Gemini
            try:
                payload = generate_post_match_article(ctx)
            except Exception as e:
                print(f"  [ERROR] AI generation failed for match {match.id}: {e}")
                continue

            if not payload:
                print(f"  [ERROR] AI returned empty payload for match {match.id}")
                continue
                
            print(f"  [SUCCESS] Generated: {payload.get('title')}")
            
            dedupe_key = f"post_match_{match.id}"
            
            # Persist it
            article = persist_article(
                db,
                payload,
                fixture_id=match.id,
                league_id=match.league_id,
                home_team_id=match.home_team_id,
                away_team_id=match.away_team_id,
                news_type="post_match",
                dedupe_key=dedupe_key,
            )
            
            if article:
                print("  [SUCCESS] Article saved to DB.")
                count += 1
            else:
                print("  [INFO] Article already existed (skipped).")
                
        print(f"News seeding process completed! Successfully generated {count} articles.")
        
    finally:
        db.close()

if __name__ == "__main__":
    seed_news()