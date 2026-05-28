"""Seed a populated Matchday Points page for the AbelC23 user.

Target matchday: 2026-05-26 (matches the screenshot used in the thesis).

What this script does:
  1. Locates the AbelC23 user (case-insensitive lookup).
  2. Ensures a 15-player squad exists for that user, building one from the
     supported league pool if missing.
  3. Inserts/updates the matchday picks (11 starters + 4 bench, captain set).
  4. Replaces the FantasyPointsHistory rows for that matchday with realistic
     per-player breakdowns (appearance, goals, assists, clean sheets,
     captain multiplier).
  5. Upserts the matching FantasyMatchdaySummary row so the leaderboard and
     /points endpoint render the same totals on the front-end.

Run:
    cd backend
    python seed_abelc23_points.py
"""

from __future__ import annotations

import os
import sys
import random
from datetime import date, datetime, timezone
from decimal import Decimal
from typing import Dict, List, Optional, Tuple

# Allow running from backend or project root.
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from sqlalchemy.orm import Session

from database import SessionLocal
from models import (
    FantasyMatchdayPick,
    FantasyMatchdaySummary,
    FantasyPlayerSquad,
    FantasyPointsHistory,
    FantasySquadPlayer,
    League,
    Player,
    Team,
    User,
)
from services.fantasy_rules_engine import (
    FANTASY_BUDGET_CAP,
    SQUAD_POSITION_LIMITS,
    SUPPORTED_LEAGUE_NAME_TOKENS,
    calculate_player_price,
    normalize_position,
)


TARGET_USERNAME = "Abel23"
TARGET_MATCHDAY = date(2026, 5, 26)
RANDOM_SEED = 26052026  # Deterministic so reruns produce the same picks.


def _find_user(db: Session) -> Optional[User]:
    user = (
        db.query(User)
        .filter(User.username.ilike(TARGET_USERNAME))
        .first()
    )
    if user:
        return user

    # Fall back to email-style lookup for resilience.
    return (
        db.query(User)
        .filter(User.email.ilike(f"%{TARGET_USERNAME}%"))
        .first()
    )


def _supported_player_pool(db: Session) -> Dict[str, List[Player]]:
    rows = (
        db.query(Player, League)
        .join(Team, Player.team_id == Team.id)
        .join(League, Team.league_id == League.id)
        .all()
    )

    pool: Dict[str, List[Player]] = {"GK": [], "DEF": [], "MID": [], "FWD": []}
    for player, league in rows:
        league_name = (league.name or "").lower() if league else ""
        if not any(token in league_name for token in SUPPORTED_LEAGUE_NAME_TOKENS):
            continue
        pos = normalize_position(player.position)
        if pos in pool:
            pool[pos].append(player)
    return pool


def _ensure_squad(db: Session, user: User) -> FantasyPlayerSquad:
    squad = (
        db.query(FantasyPlayerSquad)
        .filter(FantasyPlayerSquad.user_id == user.id)
        .first()
    )

    if squad:
        active_count = (
            db.query(FantasySquadPlayer)
            .filter(
                FantasySquadPlayer.squad_id == squad.id,
                FantasySquadPlayer.is_active.is_(True),
            )
            .count()
        )
        if active_count == sum(SQUAD_POSITION_LIMITS.values()):
            return squad

    pool = _supported_player_pool(db)
    for pos, required in SQUAD_POSITION_LIMITS.items():
        if len(pool[pos]) < required:
            raise RuntimeError(
                f"Not enough {pos} players in supported leagues "
                f"({len(pool[pos])} < {required}); ingest data first."
            )

    selected: List[Tuple[Player, str, Decimal]] = []
    used_ids: set[int] = set()
    team_counts: Dict[int, int] = {}
    total_spent = Decimal("0.00")

    for pos, count in SQUAD_POSITION_LIMITS.items():
        candidates = list(pool[pos])
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
            remaining_slots = sum(SQUAD_POSITION_LIMITS.values()) - len(selected) - 1
            if total_spent + price + Decimal("4.00") * remaining_slots > FANTASY_BUDGET_CAP:
                continue
            selected.append((player, pos, price))
            used_ids.add(player.id)
            team_counts[player.team_id] = team_counts.get(player.team_id, 0) + 1
            total_spent += price
            picked += 1
        if picked < count:
            raise RuntimeError(f"Could not fill {pos} for {user.username}: {picked}/{count}")

    if squad is None:
        squad = FantasyPlayerSquad(
            user_id=user.id,
            budget_cap=FANTASY_BUDGET_CAP,
            budget_spent=total_spent,
        )
        db.add(squad)
        db.flush()
    else:
        # Reset existing squad players before reseeding.
        db.query(FantasySquadPlayer).filter(FantasySquadPlayer.squad_id == squad.id).delete()
        squad.budget_cap = FANTASY_BUDGET_CAP
        squad.budget_spent = total_spent

    for player, pos, price in selected:
        db.add(
            FantasySquadPlayer(
                squad_id=squad.id,
                player_id=player.id,
                position_key=pos,
                purchase_price=price,
                is_active=True,
            )
        )
    db.commit()
    return squad


def _build_picks(db: Session, squad: FantasyPlayerSquad) -> Dict[str, List[FantasySquadPlayer]]:
    squad_players = (
        db.query(FantasySquadPlayer)
        .filter(
            FantasySquadPlayer.squad_id == squad.id,
            FantasySquadPlayer.is_active.is_(True),
        )
        .all()
    )

    by_pos: Dict[str, List[FantasySquadPlayer]] = {"GK": [], "DEF": [], "MID": [], "FWD": []}
    for sp in squad_players:
        by_pos[sp.position_key].append(sp)

    formation = {"GK": 1, "DEF": 4, "MID": 4, "FWD": 2}
    starters: List[FantasySquadPlayer] = []
    bench: List[FantasySquadPlayer] = []
    for pos, count in formation.items():
        slot = list(by_pos[pos])
        random.shuffle(slot)
        starters.extend(slot[:count])
        bench.extend(slot[count:])

    db.query(FantasyMatchdayPick).filter(
        FantasyMatchdayPick.squad_id == squad.id,
        FantasyMatchdayPick.matchday_key == TARGET_MATCHDAY,
    ).delete(synchronize_session=False)

    # Prefer a forward as captain so the captain bonus is meaningful when paired
    # with the seeded goal contribution; fall back to a midfielder, then to the
    # first starter if neither category is available.
    forwards_in_starters = [sp for sp in starters if sp.position_key == "FWD"]
    midfielders_in_starters = [sp for sp in starters if sp.position_key == "MID"]
    if forwards_in_starters:
        captain = forwards_in_starters[0]
    elif midfielders_in_starters:
        captain = midfielders_in_starters[0]
    else:
        captain = starters[0]

    vice_candidates = [sp for sp in starters if sp.player_id != captain.player_id]
    vice_captain = vice_candidates[0] if vice_candidates else None

    for sp in starters:
        db.add(
            FantasyMatchdayPick(
                squad_id=squad.id,
                matchday_key=TARGET_MATCHDAY,
                player_id=sp.player_id,
                role="starter",
                bench_order=None,
                is_captain=(sp.player_id == captain.player_id),
                is_vice_captain=(vice_captain is not None and sp.player_id == vice_captain.player_id),
            )
        )

    for index, sp in enumerate(bench, start=1):
        db.add(
            FantasyMatchdayPick(
                squad_id=squad.id,
                matchday_key=TARGET_MATCHDAY,
                player_id=sp.player_id,
                role="bench",
                bench_order=index,
                is_captain=False,
                is_vice_captain=False,
            )
        )

    db.commit()

    return {"starters": starters, "captain": [captain]}


def _seed_points_history(
    db: Session,
    squad: FantasyPlayerSquad,
    user: User,
    starters: List[FantasySquadPlayer],
    captain: FantasySquadPlayer,
) -> int:
    db.query(FantasyPointsHistory).filter(
        FantasyPointsHistory.squad_id == squad.id,
        FantasyPointsHistory.user_id == user.id,
        FantasyPointsHistory.matchday_key == TARGET_MATCHDAY,
    ).delete(synchronize_session=False)

    total = 0

    # Appearance bonus: every starter played.
    for sp in starters:
        db.add(
            FantasyPointsHistory(
                squad_id=squad.id,
                user_id=user.id,
                matchday_key=TARGET_MATCHDAY,
                player_id=sp.player_id,
                match_id=None,
                points=2,
                reason="appearance",
            )
        )
        total += 2

    midfielders = [sp for sp in starters if sp.position_key == "MID"]
    forwards = [sp for sp in starters if sp.position_key == "FWD"]
    defenders = [sp for sp in starters if sp.position_key == "DEF"]
    goalkeepers = [sp for sp in starters if sp.position_key == "GK"]

    # Captain scores his expected goal first so the multiplier doubles it later.
    if captain.position_key in {"FWD", "MID"}:
        captain_goal_points = 4 if captain.position_key == "FWD" else 5
        db.add(
            FantasyPointsHistory(
                squad_id=squad.id,
                user_id=user.id,
                matchday_key=TARGET_MATCHDAY,
                player_id=captain.player_id,
                match_id=None,
                points=captain_goal_points,
                reason="goal",
            )
        )
        total += captain_goal_points

    # One additional goal from the rest of the attack to spread the breakdown.
    other_attackers = [
        sp for sp in (forwards + midfielders) if sp.player_id != captain.player_id
    ]
    if other_attackers:
        scorer = other_attackers[0]
        scorer_points = 4 if scorer.position_key == "FWD" else 5
        db.add(
            FantasyPointsHistory(
                squad_id=squad.id,
                user_id=user.id,
                matchday_key=TARGET_MATCHDAY,
                player_id=scorer.player_id,
                match_id=None,
                points=scorer_points,
                reason="goal",
            )
        )
        total += scorer_points

    # Two assists from midfield/forward pool, excluding the captain so the row
    # breakdown reads naturally on the front-end.
    assist_candidates = [
        sp for sp in (midfielders + forwards) if sp.player_id != captain.player_id
    ]
    random.shuffle(assist_candidates)
    for sp in assist_candidates[:2]:
        db.add(
            FantasyPointsHistory(
                squad_id=squad.id,
                user_id=user.id,
                matchday_key=TARGET_MATCHDAY,
                player_id=sp.player_id,
                match_id=None,
                points=3,
                reason="assist",
            )
        )
        total += 3

    # Clean sheet bonuses for GK + 2 random defenders.
    clean_sheet_targets = goalkeepers + random.sample(defenders, k=min(2, len(defenders)))
    for sp in clean_sheet_targets:
        db.add(
            FantasyPointsHistory(
                squad_id=squad.id,
                user_id=user.id,
                matchday_key=TARGET_MATCHDAY,
                player_id=sp.player_id,
                match_id=None,
                points=4,
                reason="clean_sheet",
            )
        )
        total += 4

    # Captain multiplier: double the captain's contribution so far.
    db.flush()  # ensure pending inserts are visible to the next query
    captain_subtotal = (
        db.query(FantasyPointsHistory)
        .filter(
            FantasyPointsHistory.squad_id == squad.id,
            FantasyPointsHistory.user_id == user.id,
            FantasyPointsHistory.matchday_key == TARGET_MATCHDAY,
            FantasyPointsHistory.player_id == captain.player_id,
        )
        .all()
    )
    captain_bonus = sum(int(row.points) for row in captain_subtotal)
    if captain_bonus != 0:
        db.add(
            FantasyPointsHistory(
                squad_id=squad.id,
                user_id=user.id,
                matchday_key=TARGET_MATCHDAY,
                player_id=captain.player_id,
                match_id=None,
                points=captain_bonus,
                reason="captain_multiplier",
            )
        )
        total += captain_bonus

    db.commit()
    return total


def _upsert_summary(
    db: Session,
    squad: FantasyPlayerSquad,
    user: User,
    captain: FantasySquadPlayer,
    total_points: int,
) -> None:
    summary = (
        db.query(FantasyMatchdaySummary)
        .filter(
            FantasyMatchdaySummary.squad_id == squad.id,
            FantasyMatchdaySummary.matchday_key == TARGET_MATCHDAY,
        )
        .first()
    )

    if summary is None:
        summary = FantasyMatchdaySummary(
            squad_id=squad.id,
            user_id=user.id,
            matchday_key=TARGET_MATCHDAY,
            total_points=total_points,
            captain_player_id=captain.player_id,
            transfers_used=0,
            transfer_penalty=0,
            computed_at=datetime.now(timezone.utc),
        )
        db.add(summary)
    else:
        summary.total_points = total_points
        summary.captain_player_id = captain.player_id
        summary.transfers_used = 0
        summary.transfer_penalty = 0
        summary.computed_at = datetime.now(timezone.utc)

    db.commit()


def main() -> None:
    random.seed(RANDOM_SEED)
    db = SessionLocal()
    try:
        user = _find_user(db)
        if user is None:
            print(
                f"❌ Could not find user '{TARGET_USERNAME}'. "
                "Create the account first (sign in via the front-end), then rerun."
            )
            return

        print(f"👤 Seeding matchday {TARGET_MATCHDAY} for {user.username} ({user.id})")

        squad = _ensure_squad(db, user)
        groups = _build_picks(db, squad)
        starters = groups["starters"]
        captain = groups["captain"][0]

        captain_player = db.query(Player).filter(Player.id == captain.player_id).first()
        captain_label = captain_player.name if captain_player else f"#{captain.player_id}"
        print(f"🏆 Captain selected: {captain_label}")

        total = _seed_points_history(db, squad, user, starters, captain)
        _upsert_summary(db, squad, user, captain, total)

        print(f"✅ Done. Total matchday points = {total} for {user.username} on {TARGET_MATCHDAY}")
    except Exception as exc:  # noqa: BLE001
        db.rollback()
        print(f"❌ Failed: {exc}")
        raise
    finally:
        db.close()


if __name__ == "__main__":
    main()
