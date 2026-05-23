"""Generate 1X2 predictions for upcoming matches.

Tries the trained PyTorch model first (calibrated with isotonic). When
the artifact is missing - typically before the first training run - or
when feature extraction fails (insufficient history for a brand-new
team), falls back to the standings-based heuristic so the UI never goes
empty.
"""

from __future__ import annotations

import logging
from typing import Optional, Tuple

try:
    from backend.ai.match_outcome_inference import predict_for_match
    from backend.database import SessionLocal
    from backend.models import Match, Prediction, Standing
except ImportError:
    from ai.match_outcome_inference import predict_for_match  # type: ignore[no-redef]
    from database import SessionLocal  # type: ignore[no-redef]
    from models import Match, Prediction, Standing  # type: ignore[no-redef]


logger = logging.getLogger(__name__)


def _heuristic_probabilities(
    home_standing: Optional[Standing], away_standing: Optional[Standing]
) -> Tuple[float, float, float]:
    """Standings-based fallback used until the network is trained."""
    if not home_standing or not away_standing:
        return 0.45, 0.25, 0.30

    home_ppg = home_standing.points / home_standing.played if home_standing.played > 0 else 1.0
    away_ppg = away_standing.points / away_standing.played if away_standing.played > 0 else 1.0
    home_strength = home_ppg * 1.1  # Home advantage bump.
    away_strength = away_ppg
    total = home_strength + away_strength
    if total == 0:
        return 0.33, 0.34, 0.33

    home_prob = home_strength / total
    away_prob = away_strength / total

    draw_prob = 0.25
    remaining = 1.0 - draw_prob
    home_prob *= remaining
    away_prob *= remaining

    s = home_prob + draw_prob + away_prob
    return round(home_prob / s, 4), round(draw_prob / s, 4), round(away_prob / s, 4)


def generate_predictions() -> None:
    db = SessionLocal()
    try:
        matches = db.query(Match).filter(Match.status.in_(["NS", "TBD"])).all()
        logger.info("generate_predictions: %s upcoming match(es) to score", len(matches))

        ml_used = 0
        heuristic_used = 0

        for match in matches:
            existing = db.query(Prediction).filter(Prediction.match_id == match.id).first()

            ml_result = None
            try:
                ml_result = predict_for_match(db, match)
            except Exception:
                logger.exception("ML inference failed for match=%s", match.id)

            if ml_result is not None:
                home_prob, draw_prob, away_prob = ml_result
                ml_used += 1
            else:
                home_standing = (
                    db.query(Standing).filter(Standing.team_id == match.home_team_id).first()
                )
                away_standing = (
                    db.query(Standing).filter(Standing.team_id == match.away_team_id).first()
                )
                home_prob, draw_prob, away_prob = _heuristic_probabilities(home_standing, away_standing)
                heuristic_used += 1

            confidence = max(home_prob, draw_prob, away_prob)

            if existing:
                existing.home_win_prob = home_prob
                existing.draw_prob = draw_prob
                existing.away_win_prob = away_prob
                existing.confidence_score = confidence
            else:
                db.add(
                    Prediction(
                        match_id=match.id,
                        home_win_prob=home_prob,
                        draw_prob=draw_prob,
                        away_win_prob=away_prob,
                        confidence_score=confidence,
                    )
                )

        db.commit()
        logger.info(
            "generate_predictions: ml=%s heuristic=%s",
            ml_used,
            heuristic_used,
        )
    except Exception:
        db.rollback()
        logger.exception("generate_predictions failed")
    finally:
        db.close()


if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO)
    generate_predictions()
