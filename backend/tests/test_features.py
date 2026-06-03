"""Unit tests for Football-Hub backend biggest features."""
import sys
import os
from decimal import Decimal
from unittest.mock import MagicMock, patch

import pytest

# Ensure backend package is importable
sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from services.fantasy_rules_engine import (
    normalize_position,
    calculate_player_price,
    validate_squad,
    decimalize,
    FantasyRuleError,
    FANTASY_SQUAD_SIZE,
    FANTASY_BUDGET_CAP,
)


# ─── normalize_position ─────────────────────────────────────────────────────────

class TestNormalizePosition:
    def test_goalkeeper(self):
        assert normalize_position("Goalkeeper") == "GK"

    def test_defender(self):
        assert normalize_position("Centre-Back") == "DEF"

    def test_midfielder(self):
        assert normalize_position("Midfielder") == "MID"

    def test_forward(self):
        assert normalize_position("Striker") == "FWD"

    def test_none_defaults_to_mid(self):
        assert normalize_position(None) == "MID"

    def test_empty_defaults_to_mid(self):
        assert normalize_position("") == "MID"


# ─── decimalize ─────────────────────────────────────────────────────────────────

class TestDecimalize:
    def test_from_float(self):
        assert decimalize(7.5) == Decimal("7.50")

    def test_from_none(self):
        assert decimalize(None) == Decimal("0.00")

    def test_from_decimal(self):
        assert decimalize(Decimal("3.141")) == Decimal("3.14")


# ─── calculate_player_price ──────────────────────────────────────────────────────

class TestCalculatePlayerPrice:
    def _make_player(self, position="Forward", goals=10, assists=5, rating=7.5, minutes=2000):
        p = MagicMock()
        p.position = position
        p.goals_season = goals
        p.assists_season = assists
        p.rating_season = rating
        p.minutes_played = minutes
        return p

    def test_price_within_bounds(self):
        player = self._make_player()
        price = calculate_player_price(player)
        assert Decimal("4.00") <= price <= Decimal("14.50")

    def test_low_stats_minimum_price(self):
        player = self._make_player(goals=0, assists=0, rating=5.0, minutes=100)
        price = calculate_player_price(player)
        assert price >= Decimal("4.00")

    def test_high_stats_capped(self):
        player = self._make_player(goals=40, assists=20, rating=9.5, minutes=3500)
        price = calculate_player_price(player)
        assert price <= Decimal("14.50")


# ─── validate_squad ──────────────────────────────────────────────────────────────

class TestValidateSquad:
    def _make_players(self):
        """Create a valid 15-player squad: 2 GK, 5 DEF, 5 MID, 3 FWD."""
        players = []
        positions = ["GK"] * 2 + ["DEF"] * 5 + ["MID"] * 5 + ["FWD"] * 3
        for i, pos in enumerate(positions, start=1):
            p = MagicMock()
            p.id = i
            players.append(p)

        position_map = {i + 1: pos for i, pos in enumerate(positions)}
        team_map = {i + 1: (i % 5) + 1 for i in range(15)}  # spread across 5 teams
        price_map = {i + 1: Decimal("6.00") for i in range(15)}  # 90 total, under 100
        return players, position_map, team_map, price_map

    def test_valid_squad_passes(self):
        players, position_map, team_map, price_map = self._make_players()
        result = validate_squad(players, position_map, team_map, price_map)
        assert result.spent == Decimal("90.00")
        assert result.remaining == Decimal("10.00")

    def test_wrong_squad_size_raises(self):
        players, position_map, team_map, price_map = self._make_players()
        with pytest.raises(FantasyRuleError, match="exactly 15"):
            validate_squad(players[:10], position_map, team_map, price_map)

    def test_budget_exceeded_raises(self):
        players, position_map, team_map, price_map = self._make_players()
        price_map = {i + 1: Decimal("7.00") for i in range(15)}
        with pytest.raises(FantasyRuleError, match="Budget exceeded"):
            validate_squad(players, position_map, team_map, price_map)

    def test_duplicate_players_raises(self):
        players, position_map, team_map, price_map = self._make_players()
        players[1] = players[0]  # duplicate
        with pytest.raises(FantasyRuleError, match="Duplicate"):
            validate_squad(players, position_map, team_map, price_map)


# ─── Prediction heuristic ────────────────────────────────────────────────────────

class TestPredictionHeuristic:
    def test_no_standings_returns_default_probs(self):
        from generate_predictions import _heuristic_probabilities
        h, d, a = _heuristic_probabilities(None, None)
        assert abs(h + d + a - 1.0) < 0.01

    def test_equal_standings_gives_home_advantage(self):
        from generate_predictions import _heuristic_probabilities
        standing = MagicMock()
        standing.points = 30
        standing.played = 15
        h, d, a = _heuristic_probabilities(standing, standing)
        assert h > a  # home advantage


# ─── Auth: get_current_user ──────────────────────────────────────────────────────

class TestAuth:
    @pytest.mark.asyncio
    async def test_missing_supabase_raises_500(self):
        with patch("auth.supabase", None):
            from auth import get_current_user
            from fastapi import HTTPException
            with pytest.raises(HTTPException) as exc_info:
                await get_current_user(token="fake", db=MagicMock())
            assert exc_info.value.status_code == 500
