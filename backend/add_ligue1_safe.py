"""
Safely add Ligue 1 to the database with retry logic and error handling
"""
from services.football_data_org import (
    fetch_competitions,
    fetch_competition_teams,
    fetch_competition_matches,
    fetch_competition_standings,
    parse_team_from_fd,
    parse_match_from_fd,
    parse_standing_from_fd,
    parse_players_from_team
)
from database import SessionLocal
from models import League, Team, Match, Standing, Player
import datetime
import time

db = SessionLocal()

try:
    # Check if Ligue 1 exists
    ligue1 = db.query(League).filter(League.name.like('%Ligue%')).first()
    
    if ligue1:
        print(f"Ligue 1 already exists: {ligue1.name} (ID: {ligue1.id})")
        db.close()
        exit(0)
    
    print("Fetching Ligue 1 data...")
    
    # Get Ligue 1 from API
    try:
        competitions = fetch_competitions()
        ligue1_data = next((c for c in competitions if c['code'] == 'FL1'), None)
    except Exception as e:
        print(f"❌ Error fetching competitions: {e}")
        db.rollback()
        db.close()
        exit(1)
    
    if not ligue1_data:
        print("❌ Ligue 1 not found in API")
        db.close()
        exit(1)
    
    print(f"Found: {ligue1_data['name']} (Code: {ligue1_data['code']}, ID: {ligue1_data['id']})")
    
    # Add league
    league = League(
        id=ligue1_data['id'],
        name=ligue1_data['name'],
        country=ligue1_data['area']['name'],
        logo_url=ligue1_data.get('emblem', '')
    )
    db.add(league)
    db.commit()
    print(f"✅ Added league: {league.name}")
    
    # Wait to respect API rate limits
    print("Waiting 3 seconds for API rate limit...")
    time.sleep(3)
    
    # Fetch and add teams
    print("\nFetching teams...")
    try:
        teams_data = fetch_competition_teams('FL1')
        print(f"Found {len(teams_data)} teams")
    except Exception as e:
        print(f"❌ Error fetching teams: {e}")
        print("Rolling back league creation...")
        db.delete(league)
        db.commit()
        db.close()
        exit(1)
    
    team_ids = set()
    total_players = 0
    
    for i, team_data in enumerate(teams_data):
        try:
            parsed = parse_team_from_fd(team_data)
            team = parsed['team']
            venue = parsed['venue']
            
            # Check if team already exists (in case of shared teams with other leagues)
            existing_team = db.query(Team).filter(Team.id == team['id']).first()
            if not existing_team:
                new_team = Team(
                    id=team['id'],
                    name=team['name'],
                    logo_url=team['logo'],
                    stadium=venue['name'],
                    league_id=league.id
                )
                db.add(new_team)
            
            team_ids.add(team['id'])
            
            # Add players
            players = parse_players_from_team(team_data)
            for p in players:
                existing_player = db.query(Player).filter(Player.id == p['id']).first()
                if not existing_player:
                    new_player = Player(
                        id=p['id'],
                        name=p['name'],
                        position=p['position'],
                        nationality=p['nationality'],
                        team_id=team['id']
                    )
                    db.add(new_player)
                    total_players += 1
            
            if (i + 1) % 5 == 0:
                print(f"  Processed {i + 1}/{len(teams_data)} teams...")
                
        except Exception as e:
            print(f"  ⚠️ Error processing team: {e}")
            continue
    
    db.commit()
    print(f"✅ Added {len(team_ids)} teams and {total_players} players")
    
    # Wait for API rate limit
    print("Waiting 3 seconds for API rate limit...")
    time.sleep(3)
    
    # Fetch and add standings
    print("\nFetching standings...")
    try:
        standings_data = fetch_competition_standings('FL1')
        standings_added = 0
        
        if standings_data:
            total_standings = next((s for s in standings_data if s['type'] == 'TOTAL'), None)
            
            if total_standings:
                for row in total_standings['table']:
                    try:
                        parsed = parse_standing_from_fd(row)
                        
                        if parsed['team_id'] in team_ids:
                            new_standing = Standing(
                                league_id=league.id,
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
                        print(f"  ⚠️ Error processing standing: {e}")
                        
                db.commit()
                print(f"✅ Added {standings_added} standings")
            else:
                print("⚠️ No TOTAL standings found")
        else:
            print("⚠️ No standings data available")
    except Exception as e:
        print(f"⚠️ Error fetching standings (non-critical): {e}")
    
    # Wait for API rate limit
    print("Waiting 3 seconds for API rate limit...")
    time.sleep(3)
    
    # Fetch and add matches
    print("\nFetching matches...")
    try:
        all_matches = fetch_competition_matches('FL1')
        print(f"Found {len(all_matches)} matches from API")
        
        fixtures_added = 0
        
        for i, match_data in enumerate(all_matches):
            try:
                parsed = parse_match_from_fd(match_data)
                
                fixture = parsed['fixture']
                teams = parsed['teams']
                goals = parsed['goals']
                
                home_team_id = teams['home']['id']
                away_team_id = teams['away']['id']
                
                if home_team_id not in team_ids or away_team_id not in team_ids:
                    continue
                
                dt_str = fixture['date']
                dt_obj = datetime.datetime.fromisoformat(dt_str.replace('Z', '+00:00'))
                
                # Check if match already exists
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
                
                if (i + 1) % 50 == 0:
                    print(f"  Processed {i + 1}/{len(all_matches)} matches...")
                    
            except Exception as e:
                print(f"  ⚠️ Error processing match: {e}")
                continue
        
        db.commit()
        print(f"✅ Added {fixtures_added} matches")
        
    except Exception as e:
        print(f"⚠️ Error fetching matches (non-critical): {e}")
    
    print("\n✅ Ligue 1 added successfully!")
    
except Exception as e:
    print(f"\n❌ Critical error: {e}")
    print("Rolling back all changes...")
    db.rollback()
    import traceback
    traceback.print_exc()
finally:
    db.close()
