try:
    from services.football_data_org import fetch_competitions
except ImportError:
    import sys
    import os
    sys.path.append(os.path.dirname(os.path.abspath(__file__)))
    from services.football_data_org import fetch_competitions

comps = fetch_competitions()
print("Available Competitions:")
for c in comps:
    print(f"Code: {c['code']} | Name: {c['name']}")
