from services.football_data_org import fetch_competitions

comps = fetch_competitions()

print("Looking for UEFA Champions League:")
champ = [c for c in comps if 'Champions' in c['name']]
for c in champ:
    print(f"  {c['name']} - Code: {c['code']} - ID: {c['id']}")

print("\nLooking for Europa competitions:")
europa = [c for c in comps if 'Europa' in c['name'] or 'Conference' in c['name']]
for c in europa:
    print(f"  {c['name']} - Code: {c['code']} - ID: {c['id']}")

print("\nLooking for Ligue 1:")
ligue = [c for c in comps if 'Ligue' in c['name'] or 'French' in c['name'] or c['code'] == 'FL1']
for c in ligue:
    print(f"  {c['name']} - Code: {c['code']} - ID: {c['id']}")

print("\nLooking for Bundesliga:")
bundes = [c for c in comps if 'Bundesliga' in c['name'] or c['code'] == 'BL1']
for c in bundes:
    print(f"  {c['name']} - Code: {c['code']} - ID: {c['id']}")
