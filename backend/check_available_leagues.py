"""
Check available competitions from Football-Data.org API
"""
try:
    from backend.services.football_data_org import fetch_competitions
except ImportError:
    from services.football_data_org import fetch_competitions

competitions = fetch_competitions()

print("Available Competitions from Football-Data.org:")
print("=" * 70)

for comp in competitions:
    print(f"{comp['name']}")
    print(f"  Code: {comp['code']}")
    print(f"  ID: {comp['id']}")
    print(f"  Area: {comp['area']['name']}")
    print()
