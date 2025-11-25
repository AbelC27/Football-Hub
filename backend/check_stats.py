import os
import requests
from dotenv import load_dotenv

load_dotenv()

API_KEY = os.getenv("FOOTBALL_DATA_ORG_KEY")
BASE_URL = "https://api.football-data.org/v4"

headers = {
    'X-Auth-Token': API_KEY
}

def check_match_stats():
    # Fetch a finished match (e.g., Liverpool vs Brentford - ID 537785)
    url = f"{BASE_URL}/matches/537785"
    response = requests.get(url, headers=headers)
    
    if response.status_code == 200:
        data = response.json()
        print(f"Match: {data['homeTeam']['name']} vs {data['awayTeam']['name']}")
        print(f"Status: {data['status']}")
        
        # Check for statistics
        if 'statistics' in data:
            print("Statistics found!")
            print(data['statistics'])
        else:
            print("No 'statistics' field in response.")
            
        # Sometimes stats are in a separate endpoint or structure
        print("Keys in response:", data.keys())
        
    else:
        print(f"Error: {response.status_code}")

if __name__ == "__main__":
    check_match_stats()
