"""Elo rating engine for football clubs.

Standard Elo with two football-specific adjustments well-supported in the
literature (cf. ClubElo, FiveThirtyEight):

- Home advantage: the home side gets `HOME_ADVANTAGE` Elo points added
  to its rating before computing expected score, accounting for the
  observed ~60% home win rate in top-flight leagues.
- Goal-difference scaling: the K-factor is multiplied by a margin-of-
  victory term so blow-outs move ratings more than 1-0 wins, preventing
  small-sample noise from dominating updates.

The module is pure: given the chronological list of finished matches it
returns, for each fixture, the (pre, post) Elo for both teams, plus the
final rating dictionary. Persistence is handled separately.
"""

from __future__ import annotations

import math
from dataclasses import dataclass
from typing import Dict, Iterable, List, Optional, Tuple

# Initial rating granted to a team the first time we see it. Anchored at
# 1500 because that's the long-time community standard; calibration below
# normalises this away within ~10 matches per club.
DEFAULT_RATING: float = 1500.0
HOME_ADVANTAGE: float = 65.0  # Elo bonus, ~equivalent to a 0.6 goal expectation gap.
K_BASE: float = 20.0  # Updates feel meaningful without being volatile.


@dataclass(frozen=True)
class EloMatchInput:
    """Minimal info needed to update Elo for one finished fixture."""

    match_id: int
    home_team_id: int
    away_team_id: int
    home_score: int
    away_score: int


@dataclass
class EloMatchUpdate:
    """Result of applying one finished match to the running ratings."""

    match_id: int
    home_team_id: int
    away_team_id: int
    home_pre: float
    away_pre: float
    home_post: float
    away_post: float


def _expected_score(rating_a: float, rating_b: float) -> float:
    return 1.0 / (1.0 + math.pow(10.0, (rating_b - rating_a) / 400.0))


def _goal_diff_multiplier(goal_diff: int) -> float:
    """Margin-of-victory amplifier (FiveThirtyEight formula).

    Hard-clamped against runaway updates; +3 goals already matters,
    +5+ saturates so 8-0 doesn't hand out an Elo lottery prize.
    """
    if goal_diff <= 0:
        return 1.0
    return math.log1p(goal_diff) * 1.0


class EloEngine:
    """Stateful per-team rating tracker."""

    def __init__(self, default_rating: float = DEFAULT_RATING):
        self._ratings: Dict[int, float] = {}
        self._default_rating = default_rating

    def rating(self, team_id: int) -> float:
        return self._ratings.get(team_id, self._default_rating)

    def update_from_match(self, match: EloMatchInput) -> EloMatchUpdate:
        home_pre = self.rating(match.home_team_id)
        away_pre = self.rating(match.away_team_id)

        # Apply home advantage only to the *expectancy* computation, not
        # the persisted rating. This way the rating reflects the team's
        # neutral-ground strength.
        home_expected = _expected_score(home_pre + HOME_ADVANTAGE, away_pre)
        away_expected = 1.0 - home_expected

        if match.home_score > match.away_score:
            home_actual, away_actual = 1.0, 0.0
        elif match.home_score < match.away_score:
            home_actual, away_actual = 0.0, 1.0
        else:
            home_actual = away_actual = 0.5

        goal_diff = abs(match.home_score - match.away_score)
        k_eff = K_BASE * _goal_diff_multiplier(goal_diff)

        home_post = home_pre + k_eff * (home_actual - home_expected)
        away_post = away_pre + k_eff * (away_actual - away_expected)

        self._ratings[match.home_team_id] = home_post
        self._ratings[match.away_team_id] = away_post

        return EloMatchUpdate(
            match_id=match.match_id,
            home_team_id=match.home_team_id,
            away_team_id=match.away_team_id,
            home_pre=home_pre,
            away_pre=away_pre,
            home_post=home_post,
            away_post=away_post,
        )

    def replay(self, matches: Iterable[EloMatchInput]) -> List[EloMatchUpdate]:
        return [self.update_from_match(m) for m in matches]

    def snapshot(self) -> Dict[int, float]:
        return dict(self._ratings)


def expected_home_score(home_rating: float, away_rating: float) -> float:
    """Convenience wrapper used at inference time (UI predictions)."""
    return _expected_score(home_rating + HOME_ADVANTAGE, away_rating)
