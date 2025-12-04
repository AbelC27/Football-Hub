"""
Check Bundesliga data and try to fetch matches/standings
"""
from database import SessionLocal
from models import League, Team, Standing, Match
from services.football_data_org import (
    fetch_competition_matches,
    fetch_competition_standings,
    parse_match_from_fd,
    parse_standing_from_fd
)
import datetime

db = SessionLocal()

# Find Bundesliga
bundesliga = db.query(League).filter(League.id == 2002).first()

if not bundesliga:
    print("Bundesliga not found!")
    db.close()
    exit(1)

print(f"Found: {bundesliga.name} (ID: {bundesliga.id})")

# Get Bundesliga teams
bundes_teams = db.query(Team).filter(Team.league_id == bundesliga.id).all()
team_ids = set([t.id for t in bundes_teams])
print(f"Teams: {len(bundes_teams)}")

# Try to fetch standings
print("\nFetching standings...")
try:
    standings_data = fetch_competition_standings('BL1')
    
    if standings_data:
        total_standings = next((s for s in standings_data if s['type'] == 'TOTAL'), None)
        
        if total_standings:
            # Clear existing standings
            db.query(Standing).filter(Standing.league_id == bundesliga.id).delete()
            
            standings_added = 0
            for row in total_standings['table']:
                try:
                    parsed = parse_standing_from_fd(row)
                    
                    if parsed['team_id'] in team_ids:
                        new_standing = Standing(
                            league_id=bundesliga.id,
                            team_id=parsed['team_id'],
                            rank=parsed['rank'],
                            points=parsed['points'],
                            played=parsed['played'],
                            won=parsed['won'],
                            drawn=parsed['drawn'],
                            lost=parsed['lost'],
                            goals_for=parsed['goals_for'],
                            goals_against=parsed['goals_against'],
                            goal_difference=parsed['goal_difference'],
                            form=parsed['form']
                        )
                        db.add(new_standing)
                        standings_added += 1
                except Exception as e:
                    print(f"Error: {e}")
                    
            db.commit()
            print(f"✅ Added {standings_added} standings")
except Exception as e:
    print(f"❌ Error fetching standings: {e}")

# Try to fetch matches
print("\nFetching matches...")
try:
    all_matches = fetch_competition_matches('BL1')
    print(f"Found {len(all_matches)} matches from API")
    
    fixtures_added = 0
    matches_updated = 0
    
    for match_data in all_matches:
        try:
            parsed = parse_match_from_fd(match_data)
            
            fixture = parsed['fixture']
            teams = parsed['teams']
            goals = parsed['goals']
            
            home_team_id = teams['home']['id']
            away_team_id = teams['away']['id']
            
            # Only add if both teams are in our Bundesliga team list
            if home_team_id not in team_ids or away_team_id not in team_ids:
                continue
            
            dt_str = fixture['date']
            dt_obj = datetime.datetime.fromisoformat(dt_str.replace('Z', '+00:00'))
            
            existing_match = db.query(Match).filter(Match.id == fixture['id']).first()
            if not existing_match:
                new_match = Match(
                    id=fixture['id'],
                    home_team_id=home_team_id,
                    away_team_id=away_team_id,
                    start_time=dt_obj,
                    status=fixture['status']['short'],
                    home_score=goals['home'],
                    away_score=goals['away']
                )
                db.add(new_match)
                fixtures_added += 1
            else:
                existing_match.status = fixture['status']['short']
                existing_match.home_score = goals['home']
                existing_match.away_score = goals['away']
                matches_updated += 1
                
        except Exception as e:
            print(f"Error processing match: {e}")
            continue
    
    db.commit()
    print(f"✅ Added {fixtures_added} new matches, updated {matches_updated} matches")
    
except Exception as e:
    print(f"❌ Error fetching matches: {e}")

db.close()
print("\n✅ Bundesliga fix complete!")
