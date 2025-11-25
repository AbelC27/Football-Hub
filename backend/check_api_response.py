import requests

try:
    response = requests.get("http://localhost:8000/api/v1/match/537785/details")
    if response.status_code == 200:
        data = response.json()
        print(f"Match ID: {data['id']}")
        print(f"Home Team: {data['home_team_name']}")
        print(f"Home Players: {len(data['home_players'])}")
        if data['home_players']:
            print(f"First Home Player: {data['home_players'][0]}")
        print(f"Away Players: {len(data['away_players'])}")
    else:
        print(f"Error: {response.status_code}")
except Exception as e:
    print(f"Exception: {e}")
