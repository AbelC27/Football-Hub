"""
Enhanced Feature Engineering for Football Match Prediction
Extracts meaningful features from historical match data
"""

import sys
import os
sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

try:
    from backend.database import SessionLocal
    from backend.models import Match, Team
except ImportError:
    from database import SessionLocal
    from models import Match, Team

from datetime import datetime, timedelta
import numpy as np

def calculate_team_form(team_id, db, num_matches=5):
    """Calculate team form based on last N matches (3 points = win, 1 = draw, 0 = loss)"""
    recent_matches = db.query(Match).filter(
        ((Match.home_team_id == team_id) | (Match.away_team_id == team_id)) &
        (Match.status == 'FT')
    ).order_by(Match.start_time.desc()).limit(num_matches).all()
    
    if not recent_matches:
        return 0
    
    points = 0
    for match in recent_matches:
        if match.home_team_id == team_id:
            if match.home_score > match.away_score:
                points += 3
            elif match.home_score == match.away_score:
                points += 1
        else:
            if match.away_score > match.home_score:
                points += 3
            elif match.away_score == match.home_score:
                points += 1
    
    # Normalize to 0-1 range (max possible points = num_matches * 3)
    return points / (num_matches * 3)

def calculate_goals_average(team_id, db, num_matches=10, goals_type='scored'):
    """Calculate average goals scored or conceded"""
    recent_matches = db.query(Match).filter(
        ((Match.home_team_id == team_id) | (Match.away_team_id == team_id)) &
        (Match.status == 'FT') &
        (Match.home_score.isnot(None))
    ).order_by(Match.start_time.desc()).limit(num_matches).all()
    
    if not recent_matches:
        return 0
    
    total_goals = 0
    for match in recent_matches:
        if goals_type == 'scored':
            if match.home_team_id == team_id:
                total_goals += match.home_score or 0
            else:
                total_goals += match.away_score or 0
        else:  # conceded
            if match.home_team_id == team_id:
                total_goals += match.away_score or 0
            else:
                total_goals += match.home_score or 0
    
    return total_goals / len(recent_matches)

def calculate_home_away_performance(team_id, db, is_home, num_matches=5):
    """Calculate performance when playing home or away"""
    if is_home:
        matches = db.query(Match).filter(
            (Match.home_team_id == team_id) &
            (Match.status == 'FT')
        ).order_by(Match.start_time.desc()).limit(num_matches).all()
    else:
        matches = db.query(Match).filter(
            (Match.away_team_id == team_id) &
            (Match.status == 'FT')
        ).order_by(Match.start_time.desc()).limit(num_matches).all()
    
    if not matches:
        return 0
    
    points = 0
    for match in matches:
        if is_home:
            if match.home_score > match.away_score:
                points += 3
            elif match.home_score == match.away_score:
                points += 1
        else:
            if match.away_score > match.home_score:
                points += 3
            elif match.away_score == match.home_score:
                points += 1
    
    return points / (num_matches * 3)

def extract_match_features(match, db):
    """Extract all features for a match"""
    home_id = match.home_team_id
    away_id = match.away_team_id
    
    features = {
        # Team IDs (normalized)
        'home_team_id': home_id / 1000,
        'away_team_id': away_id / 1000,
        
        # Form (last 5 matches)
        'home_form': calculate_team_form(home_id, db, 5),
        'away_form': calculate_team_form(away_id, db, 5),
        
        # Goals average
        'home_goals_scored_avg': calculate_goals_average(home_id, db, 10, 'scored'),
        'away_goals_scored_avg': calculate_goals_average(away_id, db, 10, 'scored'),
        'home_goals_conceded_avg': calculate_goals_average(home_id, db, 10, 'conceded'),
        'away_goals_conceded_avg': calculate_goals_average(away_id, db, 10, 'conceded'),
        
        # Home/Away performance
        'home_home_performance': calculate_home_away_performance(home_id, db, True, 5),
        'away_away_performance': calculate_home_away_performance(away_id, db, False, 5),
        
        # Day of week (weekend games different from midweek)
        'is_weekend': 1 if match.start_time.weekday() >= 5 else 0,
    }
    
    return np.array(list(features.values()), dtype=np.float32)

def get_feature_names():
    """Return list of feature names for explainability"""
    return [
        'home_team_id',
        'away_team_id',
        'home_form',
        'away_form',
        'home_goals_scored_avg',
        'away_goals_scored_avg',
        'home_goals_conceded_avg',
        'away_goals_conceded_avg',
        'home_home_performance',
        'away_away_performance',
        'is_weekend'
    ]
