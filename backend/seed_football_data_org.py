"""
Football-Data.org Seeder
Fetches current season data from Football-Data.org API

Steps:
1. Register at https://www.football-data.org/client/register
2. Add your API key to .env as FOOTBALL_DATA_ORG_KEY=your_key_here
3. Run this script
"""
try:
    from backend.services.football_data_org import (
        fetch_competitions,
        fetch_competition_teams,
        fetch_competition_matches,
        fetch_competition_standings,
        parse_team_from_fd,
        parse_match_from_fd,
        parse_standing_from_fd,
        parse_players_from_team
    )
    from backend.database import SessionLocal, engine, Base
    from backend.models import League, Team, Match, Standing, Player
except ImportError:
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
    from database import SessionLocal, engine, Base
    from models import League, Team, Match, Standing, Player

from sqlalchemy.orm import Session
import datetime


# Drop all tables and recreate them
print("Dropping all tables...")
Base.metadata.drop_all(bind=engine)
print("Creating all tables...")
Base.metadata.create_all(bind=engine)

def seed_league(db: Session, competition_code: str, competition_name: str):
    """
    Seed a specific league data from Football-Data.org
    """
    print("\n" + "=" * 60)
    print(f"FOOTBALL-DATA.ORG SEEDER - {competition_name} ({competition_code})")
    print("=" * 60)
    
    # Step 1: Add League
    print(f"\n=== ADDING {competition_name.upper()} ===")
    competitions = fetch_competitions()
    comp_data = next((c for c in competitions if c['code'] == competition_code), None)
    
    if not comp_data:
        print(f"❌ {competition_name} ({competition_code}) not found in available competitions")
        print("Available competitions:")
        for comp in competitions:
            print(f"  - {comp['name']} ({comp['code']})")
        return 0, 0, 0, 0
    
    # Check if league already exists
    league = db.query(League).filter(League.id == comp_data['id']).first()
    if not league:
        league = League(
            id=comp_data['id'],
            name=comp_data['name'],
            country=comp_data['area']['name'],
            logo_url=comp_data.get('emblem', '')
        )
        db.add(league)
        db.commit()
        print(f"✓ Added {comp_data['name']}")
    else:
        print(f"✓ {comp_data['name']} already exists")
    
    # Step 2: Fetch and add teams (and players)
    print("\n=== FETCHING TEAMS & PLAYERS ===")
    teams_data = fetch_competition_teams(competition_code)
    print(f"Found {len(teams_data)} teams")
    
    team_ids = set()
    total_players = 0
    
    for team_data in teams_data:
        parsed = parse_team_from_fd(team_data)
        team = parsed['team']
        venue = parsed['venue']
        
        # Check if team exists
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
        else:
            # Update league_id if needed (though teams can be in multiple leagues in reality, 
            # for now we assign them to the current one being seeded if not set, 
            # or maybe we should have a many-to-many relationship later. 
            # For now, let's just ensure they exist)
            pass
            
        team_ids.add(team['id'])
        
        # Add Players (only if team was just added or we want to refresh players)
        # For simplicity, we'll skip player check for existing teams to save time, 
        # or we could delete and re-add. Let's just add if not exists.
        
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
            
    db.commit()
    print(f"✓ Processed {len(team_ids)} teams and added {total_players} new players")
    
    # Step 3: Fetch and add standings
    print("\n=== FETCHING STANDINGS ===")
    standings_data = fetch_competition_standings(competition_code)
    standings_added = 0
    
    if standings_data:
        # Usually standings are in 'standings' list, type='TOTAL' is what we want
        total_standings = next((s for s in standings_data if s['type'] == 'TOTAL'), None)
        
        if total_standings:
            # Clear existing standings for this league to avoid duplicates
            db.query(Standing).filter(Standing.league_id == league.id).delete()
            
            for row in total_standings['table']:
                try:
                    parsed = parse_standing_from_fd(row)
                    
                    # Ensure team exists (it should, but just in case)
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
                    print(f"  ⚠️ Error processing standing row: {e}")
                    continue
            db.commit()
            print(f"✓ Added {standings_added} standing entries")
        else:
            print("⚠️ No 'TOTAL' standings table found")
    else:
        print("⚠️ No standings data returned")

    # Step 4: Fetch and add matches
    print("\n=== FETCHING MATCHES ===")
    
    # Get all matches (scheduled + finished + live)
    all_matches = fetch_competition_matches(competition_code)
    print(f"Found {len(all_matches)} total matches")
    
    # Filter to only recent/upcoming matches
    fixtures_added = 0
    for match_data in all_matches:
        try:
            parsed = parse_match_from_fd(match_data)
            
            fixture = parsed['fixture']
            teams = parsed['teams']
            goals = parsed['goals']
            
            home_team_id = teams['home']['id']
            away_team_id = teams['away']['id']
            
            # Only add if both teams exist in our database (or at least we know about them)
            # Since we fetched all teams for this comp, they should be there.
            
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
                # Update status and score
                existing_match.status = fixture['status']['short']
                existing_match.home_score = goals['home']
                existing_match.away_score = goals['away']
                
        except Exception as e:
            print(f"  ⚠️ Error processing match: {e}")
            continue
    
    db.commit()
    print(f"✓ Added/Updated {fixtures_added} matches")
    
    return len(team_ids), fixtures_added, standings_added, total_players

import time

if __name__ == "__main__":
    db = SessionLocal()
    try:
        leagues_to_seed = [
            ('PL', 'Premier League'),
            ('CL', 'UEFA Champions League'),
            ('EL', 'UEFA Europa League'),
            ('CLI', 'UEFA Conference League'),
            ('SA', 'Serie A'),
            ('PD', 'La Liga'),
            ('BL1', 'Bundesliga'),
            ('FL1', 'Ligue 1')
        ]
        
        total_stats = {'teams': 0, 'matches': 0, 'standings': 0, 'players': 0}
        
        for code, name in leagues_to_seed:
            t, m, s, p = seed_league(db, code, name)
            total_stats['teams'] += t
            total_stats['matches'] += m
            total_stats['standings'] += s
            total_stats['players'] += p
            
            print("Sleeping for 10 seconds to respect API rate limits...")
            time.sleep(10)
        
        print("\n" + "=" * 60)
        print("✅ DATABASE SEEDED SUCCESSFULLY!")
        print("=" * 60)
        print(f"Total Teams: {total_stats['teams']}")
        print(f"Total Players: {total_stats['players']}")
        print(f"Total Fixtures: {total_stats['matches']}")
        print(f"Total Standings: {total_stats['standings']}")
        print("=" * 60)
        
    except Exception as e:
        print(f"\n❌ Error during seeding: {e}")
        import traceback
        traceback.print_exc()
    finally:
        db.close()

