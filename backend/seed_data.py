"""
Seed script: Populates the database with demo Users and Fantasy Football data.

Usage:
    cd backend
    python seed_data.py

What it creates:
    - 5 demo users (with Supabase-style UUIDs)
    - Fantasy squads for each user (15 players, budget-compliant)
    - Matchday picks (starting XI + bench)
    - Some transfer history
    - Points history entries

Prerequisites:
    - The database must already have leagues, teams, and players populated.
    - Run this AFTER your normal data ingestion (football-data.org sync).
"""

import sys
import os
import uuid
import random
from datetime import datetime, date, timedelta, timezone
from decimal import Decimal

# Allow running from the backend directory or project root
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from sqlalchemy.orm import Session
from database import SessionLocal, engine, Base
from models import (
    User,
    Player,
    Team,
    League,
    FantasyPlayerSquad,
    FantasySquadPlayer,
    FantasyMatchdayPick,
    FantasyTransfer,
    FantasyPointsHistory,
    FantasyMatchdaySummary,
)
from services.fantasy_rules_engine import (
    normalize_position,
    calculate_player_price,
    FANTASY_BUDGET_CAP,
    SQUAD_POSITION_LIMITS,
)

# ─── Demo Users ───────────────────────────────────────────────────────────────

DEMO_USERS = [
    {"id": str(uuid.uuid4()), "email": "alex.morgan@demo.com", "username": "alex_morgan"},
    {"id": str(uuid.uuid4()), "email": "marco.rossi@demo.com", "username": "marco_rossi"},
    {"id": str(uuid.uuid4()), "email": "sophie.muller@demo.com", "username": "sophie_muller"},
    {"id": str(uuid.uuid4()), "email": "carlos.silva@demo.com", "username": "carlos_silva"},
    {"id": str(uuid.uuid4()), "email": "emma.johnson@demo.com", "username": "emma_johnson"},
]


def create_users(db: Session) -> list[User]:
    """Create demo users if they don't already exist."""
    created = []
    for user_data in DEMO_USERS:
        existing = db.query(User).filter(User.email == user_data["email"]).first()
        if existing:
            print(f"  ⏭  User '{user_data['username']}' already exists, skipping.")
            created.append(existing)
            continue

        user = User(
            id=user_data["id"],
            email=user_data["email"],
            username=user_data["username"],
            created_at=datetime.now(timezone.utc) - timedelta(days=random.randint(7, 60)),
        )
        db.add(user)
        created.append(user)
        print(f"  ✅ Created user '{user_data['username']}'")

    db.commit()
    return created


def get_eligible_players(db: Session) -> dict[str, list[Player]]:
    """Get players grouped by normalized position from supported leagues."""
    # Get all players that have a team
    players = (
        db.query(Player)
        .join(Team, Player.team_id == Team.id)
        .filter(Player.team_id.isnot(None))
        .all()
    )

    grouped: dict[str, list[Player]] = {"GK": [], "DEF": [], "MID": [], "FWD": []}

    for player in players:
        pos = normalize_position(player.position)
        grouped[pos].append(player)

    return grouped


def build_squad_for_user(
    db: Session, user: User, player_pool: dict[str, list[Player]]
) -> FantasyPlayerSquad | None:
    """Build a valid 15-player squad for a user within budget."""

    # Check if user already has a squad
    existing = db.query(FantasyPlayerSquad).filter(FantasyPlayerSquad.user_id == user.id).first()
    if existing:
        print(f"  ⏭  Squad already exists for '{user.username}', skipping.")
        return existing

    # Check we have enough players
    for pos, required in SQUAD_POSITION_LIMITS.items():
        if len(player_pool[pos]) < required:
            print(f"  ⚠️  Not enough {pos} players in DB ({len(player_pool[pos])} < {required}). Skipping squad for '{user.username}'.")
            return None

    # Pick players respecting position limits and max 3 per team
    selected_players: list[tuple[Player, str, Decimal]] = []
    team_counts: dict[int, int] = {}
    used_ids: set[int] = set()
    total_spent = Decimal("0.00")

    for pos, count in SQUAD_POSITION_LIMITS.items():
        # Shuffle to get variety between users
        candidates = list(player_pool[pos])
        random.shuffle(candidates)

        picked = 0
        for player in candidates:
            if picked >= count:
                break
            if player.id in used_ids:
                continue
            if team_counts.get(player.team_id, 0) >= 3:
                continue

            price = calculate_player_price(player)
            if total_spent + price > FANTASY_BUDGET_CAP - Decimal("4.00") * (
                sum(SQUAD_POSITION_LIMITS.values()) - len(selected_players) - 1
            ):
                # Skip expensive players if budget is tight
                # (leave at least 4.00 per remaining slot)
                continue

            selected_players.append((player, pos, price))
            used_ids.add(player.id)
            team_counts[player.team_id] = team_counts.get(player.team_id, 0) + 1
            total_spent += price
            picked += 1

        if picked < count:
            print(f"  ⚠️  Could only pick {picked}/{count} {pos} players for '{user.username}'. Skipping.")
            return None

    # Create the squad
    squad = FantasyPlayerSquad(
        user_id=user.id,
        budget_cap=FANTASY_BUDGET_CAP,
        budget_spent=total_spent,
        created_at=datetime.now(timezone.utc) - timedelta(days=random.randint(3, 30)),
        updated_at=datetime.now(timezone.utc),
    )
    db.add(squad)
    db.flush()  # Get the squad ID

    # Add players to squad
    for player, pos, price in selected_players:
        squad_player = FantasySquadPlayer(
            squad_id=squad.id,
            player_id=player.id,
            position_key=pos,
            purchase_price=price,
            is_active=True,
            acquired_at=squad.created_at,
        )
        db.add(squad_player)

    db.commit()
    print(f"  ✅ Created squad for '{user.username}' — {len(selected_players)} players, spent {total_spent}/{FANTASY_BUDGET_CAP}")
    return squad


def create_matchday_picks(db: Session, squad: FantasyPlayerSquad, user: User):
    """Create matchday picks (starting XI + 4 bench) for a recent matchday."""
    matchday_key = date.today() - timedelta(days=random.randint(1, 5))

    # Check if picks already exist
    existing = (
        db.query(FantasyMatchdayPick)
        .filter(
            FantasyMatchdayPick.squad_id == squad.id,
            FantasyMatchdayPick.matchday_key == matchday_key,
        )
        .first()
    )
    if existing:
        return

    # Get active squad players
    squad_players = (
        db.query(FantasySquadPlayer)
        .filter(FantasySquadPlayer.squad_id == squad.id, FantasySquadPlayer.is_active == True)
        .all()
    )

    if len(squad_players) < 15:
        return

    # Group by position
    by_pos: dict[str, list[FantasySquadPlayer]] = {"GK": [], "DEF": [], "MID": [], "FWD": []}
    for sp in squad_players:
        by_pos[sp.position_key].append(sp)

    # Build starting XI: 1 GK, 4 DEF, 4 MID, 2 FWD (standard 4-4-2)
    starters: list[FantasySquadPlayer] = []
    bench: list[FantasySquadPlayer] = []

    formations = [
        {"GK": 1, "DEF": 4, "MID": 4, "FWD": 2},
        {"GK": 1, "DEF": 4, "MID": 3, "FWD": 3},
        {"GK": 1, "DEF": 3, "MID": 5, "FWD": 2},
        {"GK": 1, "DEF": 3, "MID": 4, "FWD": 3},
    ]
    formation = random.choice(formations)

    for pos, count in formation.items():
        pos_players = by_pos[pos]
        random.shuffle(pos_players)
        starters.extend(pos_players[:count])
        bench.extend(pos_players[count:])

    # Assign captain and vice-captain from starters
    captain = random.choice(starters)
    vice_candidates = [s for s in starters if s != captain]
    vice_captain = random.choice(vice_candidates) if vice_candidates else None

    # Create pick records
    for sp in starters:
        pick = FantasyMatchdayPick(
            squad_id=squad.id,
            matchday_key=matchday_key,
            player_id=sp.player_id,
            role="starter",
            bench_order=None,
            is_captain=(sp == captain),
            is_vice_captain=(sp == vice_captain),
            created_at=datetime.now(timezone.utc),
            updated_at=datetime.now(timezone.utc),
        )
        db.add(pick)

    for i, sp in enumerate(bench, start=1):
        pick = FantasyMatchdayPick(
            squad_id=squad.id,
            matchday_key=matchday_key,
            player_id=sp.player_id,
            role="bench",
            bench_order=i,
            is_captain=False,
            is_vice_captain=False,
            created_at=datetime.now(timezone.utc),
            updated_at=datetime.now(timezone.utc),
        )
        db.add(pick)

    db.commit()
    print(f"  ✅ Created matchday picks for '{user.username}' on {matchday_key}")


def create_points_history(db: Session, squad: FantasyPlayerSquad, user: User):
    """Generate some sample points history entries."""
    matchday_key = date.today() - timedelta(days=random.randint(6, 14))

    existing = (
        db.query(FantasyPointsHistory)
        .filter(
            FantasyPointsHistory.squad_id == squad.id,
            FantasyPointsHistory.matchday_key == matchday_key,
        )
        .first()
    )
    if existing:
        return

    squad_players = (
        db.query(FantasySquadPlayer)
        .filter(FantasySquadPlayer.squad_id == squad.id, FantasySquadPlayer.is_active == True)
        .all()
    )

    total_points = 0
    reasons = ["appearance", "goal", "assist", "clean_sheet", "captain_multiplier"]

    # Give points to ~8 random players
    scorers = random.sample(squad_players, min(8, len(squad_players)))
    for sp in scorers:
        reason = random.choice(reasons)
        points = {
            "appearance": 2,
            "goal": random.choice([4, 5, 6]),
            "assist": 3,
            "clean_sheet": 4,
            "captain_multiplier": random.randint(2, 6),
        }[reason]

        entry = FantasyPointsHistory(
            squad_id=squad.id,
            user_id=user.id,
            matchday_key=matchday_key,
            player_id=sp.player_id,
            match_id=None,  # No specific match linked for demo
            points=points,
            reason=reason,
            created_at=datetime.now(timezone.utc),
        )
        db.add(entry)
        total_points += points

    # Create summary
    existing_summary = (
        db.query(FantasyMatchdaySummary)
        .filter(
            FantasyMatchdaySummary.squad_id == squad.id,
            FantasyMatchdaySummary.matchday_key == matchday_key,
        )
        .first()
    )
    if not existing_summary:
        summary = FantasyMatchdaySummary(
            squad_id=squad.id,
            user_id=user.id,
            matchday_key=matchday_key,
            total_points=total_points,
            captain_player_id=scorers[0].player_id if scorers else None,
            transfers_used=0,
            transfer_penalty=0,
            computed_at=datetime.now(timezone.utc),
        )
        db.add(summary)

    db.commit()
    print(f"  ✅ Created points history for '{user.username}' — {total_points} pts on {matchday_key}")


def create_transfers(db: Session, squad: FantasyPlayerSquad, user: User, player_pool: dict[str, list[Player]]):
    """Create 1-2 sample transfers for a user."""
    existing = db.query(FantasyTransfer).filter(FantasyTransfer.squad_id == squad.id).first()
    if existing:
        return

    active_players = (
        db.query(FantasySquadPlayer)
        .filter(FantasySquadPlayer.squad_id == squad.id, FantasySquadPlayer.is_active == True)
        .all()
    )

    if len(active_players) < 2:
        return

    # Pick 1-2 players to transfer out
    num_transfers = random.randint(1, 2)
    out_players = random.sample(active_players, num_transfers)
    matchday_key = date.today() - timedelta(days=random.randint(1, 7))

    active_ids = {sp.player_id for sp in active_players}

    for out_sp in out_players:
        pos = out_sp.position_key
        candidates = [p for p in player_pool[pos] if p.id not in active_ids]
        if not candidates:
            continue

        in_player = random.choice(candidates)
        price_out = out_sp.purchase_price
        price_in = calculate_player_price(in_player)

        transfer = FantasyTransfer(
            squad_id=squad.id,
            matchday_key=matchday_key,
            out_player_id=out_sp.player_id,
            in_player_id=in_player.id,
            price_out=price_out,
            price_in=price_in,
            penalty_points=0,
            created_at=datetime.now(timezone.utc),
        )
        db.add(transfer)
        active_ids.add(in_player.id)

    db.commit()
    print(f"  ✅ Created {num_transfers} transfer(s) for '{user.username}'")


def assign_favorite_teams(db: Session, users: list[User]):
    """Assign random favorite teams to users who don't have one."""
    teams = db.query(Team).limit(20).all()
    if not teams:
        return

    for user in users:
        if user.favorite_team_id is None:
            team = random.choice(teams)
            user.favorite_team_id = team.id
            print(f"  ✅ Set favorite team for '{user.username}' → {team.name}")

    db.commit()


def main():
    print("\n🌱 TerraBall Seed Script")
    print("=" * 50)

    db = SessionLocal()

    try:
        # 1. Create users
        print("\n📋 Creating demo users...")
        users = create_users(db)

        # 2. Assign favorite teams
        print("\n⚽ Assigning favorite teams...")
        assign_favorite_teams(db, users)

        # 3. Get player pool
        print("\n🔍 Loading player pool...")
        player_pool = get_eligible_players(db)
        for pos, players in player_pool.items():
            print(f"  {pos}: {len(players)} players available")

        total_players = sum(len(p) for p in player_pool.values())
        if total_players < 50:
            print("\n⚠️  Not enough players in the database to build fantasy squads.")
            print("   Run your data ingestion first (football-data.org sync), then re-run this script.")
            return

        # 4. Build fantasy squads
        print("\n🏗️  Building fantasy squads...")
        squads: list[tuple[FantasyPlayerSquad, User]] = []
        for user in users:
            squad = build_squad_for_user(db, user, player_pool)
            if squad:
                squads.append((squad, user))

        # 5. Create matchday picks
        print("\n📝 Creating matchday picks...")
        for squad, user in squads:
            create_matchday_picks(db, squad, user)

        # 6. Create points history
        print("\n🏆 Generating points history...")
        for squad, user in squads:
            create_points_history(db, squad, user)

        # 7. Create transfers
        print("\n🔄 Creating transfer history...")
        for squad, user in squads:
            create_transfers(db, squad, user, player_pool)

        print("\n" + "=" * 50)
        print("✅ Seeding complete!")
        print(f"   Users: {len(users)}")
        print(f"   Squads: {len(squads)}")
        print(f"   Total players in pool: {total_players}")
        print("\n💡 Note: These are demo users with random UUIDs.")
        print("   They won't have valid Supabase auth tokens,")
        print("   but they'll show up in leaderboards and DB queries.")

    except Exception as e:
        db.rollback()
        print(f"\n❌ Error: {e}")
        raise
    finally:
        db.close()


if __name__ == "__main__":
    main()
