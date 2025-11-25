import requests
from backend.models import Match
from backend.database import SessionLocal

def test_api_response():
    # We can test directly via DB or API. API is better to check serialization.
    # But API requires running server.
    # I'll check DB first to see if relationship works.
    db = SessionLocal()
    try:
        match = db.query(Match).filter(Match.status == 'NS').first()
        if match:
            print(f"Match: {match.id}")
            if match.prediction:
                print(f"Prediction: {match.prediction.home_win_prob}%")
            else:
                print("No prediction found via relationship.")
        else:
            print("No NS match found.")
    finally:
        db.close()

if __name__ == "__main__":
    test_api_response()
