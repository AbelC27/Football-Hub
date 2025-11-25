"""
Generate Predictions Script
Calculates win probabilities based on team standings and form.
"""
from database import SessionLocal
from models import Match, Team, Standing, Prediction
import random

def calculate_probabilities(home_standing, away_standing):
    """
    Calculate win probabilities based on standings.
    Returns (home_prob, draw_prob, away_prob)
    """
    if not home_standing or not away_standing:
        # Default if no data (e.g. start of season)
        return 0.45, 0.25, 0.30
    
    # Base strength on points per game
    home_ppg = home_standing.points / home_standing.played if home_standing.played > 0 else 1.0
    away_ppg = away_standing.points / away_standing.played if away_standing.played > 0 else 1.0
    
    # Adjust for home advantage (+10% strength)
    home_strength = home_ppg * 1.1
    away_strength = away_ppg
    
    total_strength = home_strength + away_strength
    
    if total_strength == 0:
        return 0.33, 0.34, 0.33
        
    home_prob = home_strength / total_strength
    away_prob = away_strength / total_strength
    
    # Adjust for draw probability (usually around 25-30%)
    draw_prob = 0.25
    
    # Normalize remaining probability
    remaining = 1.0 - draw_prob
    home_prob = home_prob * remaining
    away_prob = away_prob * remaining
    
    # Add some randomness/uncertainty
    # home_prob += random.uniform(-0.05, 0.05)
    # away_prob += random.uniform(-0.05, 0.05)
    
    # Re-normalize
    total = home_prob + draw_prob + away_prob
    home_prob /= total
    draw_prob /= total
    away_prob /= total
    
    return round(home_prob, 2), round(draw_prob, 2), round(away_prob, 2)

def generate_predictions():
    db = SessionLocal()
    try:
        print("Generating predictions for upcoming matches...")
        
        # Get matches that are Scheduled (NS) or Timed
        matches = db.query(Match).filter(Match.status.in_(['NS', 'TBD'])).all()
        print(f"Found {len(matches)} upcoming matches.")
        
        count = 0
        for match in matches:
            # Check if prediction already exists
            existing = db.query(Prediction).filter(Prediction.match_id == match.id).first()
            if existing:
                continue
                
            # Get standings
            home_standing = db.query(Standing).filter(
                Standing.team_id == match.home_team_id
            ).first()
            
            away_standing = db.query(Standing).filter(
                Standing.team_id == match.away_team_id
            ).first()
            
            home_prob, draw_prob, away_prob = calculate_probabilities(home_standing, away_standing)
            
            prediction = Prediction(
                match_id=match.id,
                home_win_prob=home_prob,
                draw_prob=draw_prob,
                away_win_prob=away_prob,
                confidence_score=max(home_prob, away_prob) # Simple confidence metric
            )
            db.add(prediction)
            count += 1
            
        db.commit()
        print(f"✓ Generated {count} predictions.")
        
    except Exception as e:
        print(f"Error: {e}")
    finally:
        db.close()

if __name__ == "__main__":
    generate_predictions()
