"""
Seed FIFA World Cup 2026 data from football-data.org.

Seeds:
  1. WC league entry
  2. All 48 teams with squads (players)
  3. All 104 matches with stage/group metadata

Run: python seed_world_cup.py
"""
import datetime
import sys

try:
    from backend.services.football_data_org import (
        fetch_competitions,
        fetch_competition_teams,
        fetch_competition_season_matches,
        parse_team_from_fd,
        parse_match_from_fd,
        parse_players_from_team,
    )
    from backend.database import SessionLocal, engine, Base
    from backend.models import League, Team, Match, Player
except ImportError:
    from services.football_data_org import (
        fetch_competitions,
        fetch_competition_teams,
        fetch_competition_season_matches,
        parse_team_from_fd,
        parse_match_from_fd,
        parse_players_from_team,
    )
    from database import SessionLocal, engine, Base
    from models import League, Team, Match, Player

Base.metadata.create_all(bind=engine)


def seed_world_cup():
    db = SessionLocal()
    try:
        # 1. Upsert league
        print("=== FIFA World Cup 2026 Seeder ===\n")
        competitions = fetch_competitions()
        wc = next((c for c in competitions if c.get("code") == "WC"), None)
        if not wc:
            print("❌ World Cup (WC) not found in available competitions")
            sys.exit(1)

        league_id = wc["id"]
        league = db.query(League).filter(League.id == league_id).first()
        if not league:
            league = League(
                id=league_id,
                name=wc["name"],
                country=wc.get("area", {}).get("name", "World"),
                logo_url=wc.get("emblem", ""),
            )
            db.add(league)
            db.commit()
            print(f"✓ Created league: {wc['name']} (id={league_id})")
        else:
            print(f"✓ League already exists: {league.name} (id={league_id})")

        # 2. Teams & players
        print("\n=== Fetching teams & squads ===")
        teams_data = fetch_competition_teams("WC")
        print(f"  Found {len(teams_data)} teams")

        players_added = 0
        seen_players = set()
        for td in teams_data:
            parsed = parse_team_from_fd(td)
            t = parsed["team"]
            venue = parsed["venue"]

            existing = db.query(Team).filter(Team.id == t["id"]).first()
            if not existing:
                db.add(Team(
                    id=t["id"], name=t["name"], logo_url=t["logo"],
                    stadium=venue["name"], league_id=league_id,
                ))
            else:
                existing.name = t["name"]
                existing.logo_url = t["logo"]
                existing.league_id = league_id

            for p in parse_players_from_team(td):
                if p["id"] in seen_players:
                    continue
                seen_players.add(p["id"])
                if not db.query(Player).filter(Player.id == p["id"]).first():
                    db.add(Player(
                        id=p["id"], name=p["name"], position=p["position"],
                        nationality=p.get("nationality"), team_id=t["id"],
                    ))
                    players_added += 1

        db.commit()
        print(f"  ✓ {len(teams_data)} teams, {players_added} new players")

        # 3. Matches
        print("\n=== Fetching matches (full season) ===")
        all_matches = fetch_competition_season_matches("WC", season=2026)
        print(f"  Found {len(all_matches)} matches")

        added = 0
        updated = 0
        skipped = 0
        for md in all_matches:
            try:
                parsed = parse_match_from_fd(md)
                fix = parsed["fixture"]
                teams = parsed["teams"]
                goals = parsed["goals"]

                h_id = teams["home"]["id"]
                a_id = teams["away"]["id"]
                if not h_id or not a_id:
                    skipped += 1
                    continue

                # Ensure teams exist (knockout may reference new ones)
                for side in (teams["home"], teams["away"]):
                    if not db.query(Team).filter(Team.id == side["id"]).first():
                        db.add(Team(
                            id=side["id"], name=side.get("name", "TBD"),
                            logo_url=side.get("logo", ""), stadium="Unknown",
                            league_id=league_id,
                        ))
                        db.flush()

                dt = datetime.datetime.fromisoformat(fix["date"].replace("Z", "+00:00"))
                existing = db.query(Match).filter(Match.id == fix["id"]).first()

                if not existing:
                    db.add(Match(
                        id=fix["id"], league_id=league_id,
                        home_team_id=h_id, away_team_id=a_id,
                        start_time=dt, status=fix["status"]["short"],
                        home_score=goals["home"], away_score=goals["away"],
                        stage=fix.get("stage"), group_name=fix.get("group_name"),
                    ))
                    added += 1
                else:
                    existing.league_id = league_id
                    existing.status = fix["status"]["short"]
                    existing.home_score = goals["home"]
                    existing.away_score = goals["away"]
                    existing.stage = fix.get("stage") or existing.stage
                    existing.group_name = fix.get("group_name") or existing.group_name
                    updated += 1
            except Exception as e:
                print(f"  ⚠️ Skipping match: {e}")
                skipped += 1
                continue

        db.commit()
        print(f"  ✓ Added {added}, updated {updated}, skipped {skipped}")
        print(f"\n✅ World Cup 2026 seed complete! League ID = {league_id}")

    except Exception as e:
        db.rollback()
        print(f"❌ Error: {e}")
        raise
    finally:
        db.close()


if __name__ == "__main__":
    seed_world_cup()
