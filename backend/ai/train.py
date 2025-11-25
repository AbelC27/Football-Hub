"""
Enhanced AI Training Script with Better Features
"""

import torch
import torch.nn as nn
import torch.optim as optim
from torch.utils.data import DataLoader
import sys
import os

# Add parent directory to path for imports
sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

try:
    from backend.database import SessionLocal
    from backend.models import Match, Prediction
    from backend.ai.model import FootballPredictor
    from backend.ai.dataset import FootballDataset
    from backend.ai.features import extract_match_features, get_feature_names
except ImportError:
    from database import SessionLocal
    from models import Match, Prediction
    from ai.model import FootballPredictor
    from ai.dataset import FootballDataset
    from ai.features import extract_match_features, get_feature_names

import numpy as np
from datetime import datetime

def prepare_training_data():
    """Prepare training data using enhanced features"""
    db = SessionLocal()
    try:
        # Get finished matches with scores
        matches = db.query(Match).filter(
            Match.status == 'FT',
            Match.home_score.isnot(None),
            Match.away_score.isnot(None)
        ).all()
        
        print(f"Found {len(matches)} finished matches for training")
        
        if len(matches) < 10:
            print("⚠️  Not enough data for training. Need at least 10 finished matches.")
            return None, None
        
        X = []
        y = []
        
        for match in matches:
            # Extract features using new feature engineering
            features = extract_match_features(match, db)
            X.append(features)
            
            # Determine outcome: 0=Home Win, 1=Draw, 2=Away Win
            if match.home_score > match.away_score:
                outcome = 0
            elif match.home_score == match.away_score:
                outcome = 1
            else:
                outcome = 2
            y.append(outcome)
        
        X = np.array(X, dtype=np.float32)
        y = np.array(y, dtype=np.int64)
        
        print(f"Training data shape: X={X.shape}, y={y.shape}")
        print(f"Feature names: {get_feature_names()}")
        print(f"Class distribution: {np.bincount(y)}")
        
        return X, y
        
    finally:
        db.close()

def train_model():
    """Train the model with enhanced features"""
    print("=" * 50)
    print("Training Enhanced Football Prediction Model")
    print("=" * 50)
    
    # Prepare data
    X, y = prepare_training_data()
    if X is None:
        return
    
    # Create dataset and dataloader
    dataset = FootballDataset(X, y)
    dataloader = DataLoader(dataset, batch_size=16, shuffle=True)
    
    # Initialize model
    model = FootballPredictor(input_size=11)
    criterion = nn.CrossEntropyLoss()
    optimizer = optim.Adam(model.parameters(), lr=0.001)
    
    # Training loop
    num_epochs = 100
    best_loss = float('inf')
    
    for epoch in range(num_epochs):
        total_loss = 0
        correct = 0
        total = 0
        
        for features_, labels_ in dataloader:
            optimizer.zero_grad()
            outputs = model(features_)
            loss = criterion(outputs, labels_)
            loss.backward()
            optimizer.step()
            
            total_loss += loss.item()
            
            # Calculate accuracy
            _, predicted = torch.max(outputs.data, 1)
            total += labels_.size(0)
            correct += (predicted == labels_).sum().item()
        
        avg_loss = total_loss / len(dataloader)
        accuracy = 100 * correct / total
        
        if (epoch + 1) % 10 == 0:
            print(f"Epoch [{epoch+1}/{num_epochs}], Loss: {avg_loss:.4f}, Accuracy: {accuracy:.2f}%")
        
        # Save best model
        if avg_loss < best_loss:
            best_loss = avg_loss
            torch.save(model.state_dict(), 'ai/football_model.pth')
    
    print(f"\n✅ Training complete! Best Loss: {best_loss:.4f}")
    print(f"Model saved to: ai/football_model.pth")
    
    return model

def generate_predictions_for_upcoming_matches(model):
    """Generate predictions for upcoming matches with explanations"""
    db = SessionLocal()
    try:
        # Get upcoming matches (status = 'NS' - Not Started)
        upcoming_matches = db.query(Match).filter(Match.status == 'NS').all()
        
        print(f"\nGenerating predictions for {len(upcoming_matches)} upcoming matches...")
        
        model.eval()
        with torch.no_grad():
            for match in upcoming_matches:
                # Extract features
                features = extract_match_features(match, db)
                features_tensor = torch.FloatTensor(features).unsqueeze(0)
                
                # Get prediction
                output = model(features_tensor)
                probabilities = torch.softmax(output, dim=1)[0]
                
                home_prob = float(probabilities[0])
                draw_prob = float(probabilities[1])
                away_prob = float(probabilities[2])
                
                # Calculate confidence (max probability)
                confidence = max(home_prob, draw_prob, away_prob)
                
                # Check if prediction already exists
                existing = db.query(Prediction).filter(Prediction.match_id == match.id).first()
                
                if existing:
                    # Update existing prediction
                    existing.home_win_prob = home_prob
                    existing.draw_prob = draw_prob
                    existing.away_win_prob = away_prob
                    existing.confidence_score = confidence
                else:
                    # Create new prediction
                    prediction = Prediction(
                        match_id=match.id,
                        home_win_prob=home_prob,
                        draw_prob=draw_prob,
                        away_win_prob=away_prob,
                        confidence_score=confidence
                    )
                    db.add(prediction)
                
                # Print prediction with reasoning
                pred_class = 'HOME WIN' if home_prob == max(home_prob, draw_prob, away_prob) else ('DRAW' if draw_prob == max(home_prob, draw_prob, away_prob) else 'AWAY WIN')
                print(f"Match {match.id}: {pred_class} (Confidence: {confidence:.2%})")
                print(f"  Probabilities: Home={home_prob:.2%}, Draw={draw_prob:.2%}, Away={away_prob:.2%}")
        
        db.commit()
        print(f"✅ Predictions saved to database!")
        
    finally:
        db.close()

if __name__ == "__main__":
    # Train the model
    model = train_model()
    
    if model:
        # Generate predictions
        generate_predictions_for_upcoming_matches(model)
        
        print("\n" + "=" * 50)
        print("Training and Prediction Generation Complete!")
        print("=" * 50)
