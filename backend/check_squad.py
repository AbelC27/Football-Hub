import os
import requests
from dotenv import load_dotenv

load_dotenv()

API_KEY = os.getenv("FOOTBALL_DATA_ORG_KEY")
BASE_URL = "https://api.football-data.org/v4"

headers = {
    'X-Auth-Token': API_KEY
}

def check_team_squad():
    # Fetch one team (e.g., Manchester City - ID 65)
    url = f"{BASE_URL}/teams/65"
    response = requests.get(url, headers=headers)
    
    if response.status_code == 200:
        data = response.json()
        print(f"Team: {data.get('name')}")
        squad = data.get('squad', [])
        print(f"Squad size: {len(squad)}")
        if squad:
            print("First player:", squad[0])
    else:
        print(f"Error: {response.status_code}")

if __name__ == "__main__":
    check_team_squad()
