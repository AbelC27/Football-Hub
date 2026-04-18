import unittest
from datetime import datetime, timedelta

from fastapi import FastAPI
from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

try:
    from backend.database import Base, get_db
    from backend.models import League, Team, Match, Prediction, Player, MatchEvent
    from backend.routers.api import router as api_router
except ImportError:
    from database import Base, get_db
    from models import League, Team, Match, Prediction, Player, MatchEvent
    from routers.api import router as api_router


class MatchExperienceContractTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.engine = create_engine(
            "sqlite://",
            connect_args={"check_same_thread": False},
            poolclass=StaticPool,
        )
        cls.SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=cls.engine)
        Base.metadata.create_all(bind=cls.engine)

        app = FastAPI()
        app.include_router(api_router)

        def override_get_db():
            db = cls.SessionLocal()
            try:
                yield db
            finally:
                db.close()

        app.dependency_overrides[get_db] = override_get_db
        cls.client = TestClient(app)

    def setUp(self):
        Base.metadata.drop_all(bind=self.engine)
        Base.metadata.create_all(bind=self.engine)
        self._seed_supported_match_fixture()
        self._seed_out_of_scope_match_fixture()

    def _seed_supported_match_fixture(self):
        db = self.SessionLocal()
        try:
            league = League(id=39, name="Premier League", country="England", logo_url="league-logo")
            db.add(league)

            home = Team(id=1001, name="Home FC", logo_url="home-logo", stadium="Home Stadium", league_id=39)
            away = Team(id=1002, name="Away FC", logo_url="away-logo", stadium="Away Stadium", league_id=39)
            opponents = [
                Team(id=1100 + idx, name=f"Opponent {idx}", logo_url=None, stadium="Opp Stadium", league_id=39)
                for idx in range(1, 8)
            ]
            db.add_all([home, away, *opponents])

            match = Match(
                id=5000,
                home_team_id=home.id,
                away_team_id=away.id,
                start_time=datetime.utcnow() + timedelta(hours=2),
                status="NS",
                home_score=None,
                away_score=None,
            )
            db.add(match)

            prediction = Prediction(
                id=9000,
                match_id=match.id,
                home_win_prob=47.5,
                draw_prob=25.0,
                away_win_prob=27.5,
                confidence_score=0.71,
            )
            db.add(prediction)

            home_players = [
                Player(id=2000 + idx, name=f"Home Player {idx}", position="Midfielder", team_id=home.id, photo_url=None)
                for idx in range(1, 14)
            ]
            away_players = [
                Player(id=3000 + idx, name=f"Away Player {idx}", position="Defender", team_id=away.id, photo_url=None)
                for idx in range(1, 14)
            ]
            db.add_all(home_players + away_players)

            events = [
                MatchEvent(
                    id=8001,
                    match_id=match.id,
                    minute=19,
                    event_type="Goal",
                    team_id=home.id,
                    player_name="Home Player 1",
                    detail="Open Play Goal",
                ),
                MatchEvent(
                    id=8002,
                    match_id=match.id,
                    minute=34,
                    event_type="Card",
                    team_id=away.id,
                    player_name="Away Player 4",
                    detail="Yellow Card",
                ),
                MatchEvent(
                    id=8003,
                    match_id=match.id,
                    minute=68,
                    event_type="Subst",
                    team_id=home.id,
                    player_name="Home Player 12",
                    detail="Home Player 12 in for Home Player 6",
                ),
            ]
            db.add_all(events)

            # Extra finished matches to validate last-5 logic for both teams.
            recent_times = [datetime.utcnow() - timedelta(days=idx) for idx in range(1, 8)]
            for idx, opponent in enumerate(opponents[:5], start=1):
                db.add(
                    Match(
                        id=5100 + idx,
                        home_team_id=home.id,
                        away_team_id=opponent.id,
                        start_time=recent_times[idx - 1],
                        status="FT",
                        home_score=idx % 3,
                        away_score=(idx + 1) % 2,
                    )
                )
                db.add(
                    Match(
                        id=5200 + idx,
                        home_team_id=opponent.id,
                        away_team_id=away.id,
                        start_time=recent_times[idx - 1] - timedelta(hours=3),
                        status="FT",
                        home_score=(idx + 2) % 3,
                        away_score=idx % 2,
                    )
                )

            db.commit()
        finally:
            db.close()

    def _seed_out_of_scope_match_fixture(self):
        db = self.SessionLocal()
        try:
            out_scope_league = League(id=9999, name="MLS", country="USA", logo_url=None)
            db.add(out_scope_league)

            home = Team(id=9001, name="Scope Home", logo_url=None, stadium="Scope Stadium", league_id=9999)
            away = Team(id=9002, name="Scope Away", logo_url=None, stadium="Scope Stadium", league_id=9999)
            db.add_all([home, away])

            match = Match(
                id=9990,
                home_team_id=home.id,
                away_team_id=away.id,
                start_time=datetime.utcnow(),
                status="NS",
                home_score=None,
                away_score=None,
            )
            db.add(match)
            db.commit()
        finally:
            db.close()

    def test_match_experience_contract_contains_required_sections(self):
        response = self.client.get("/api/v1/match/5000/experience")
        self.assertEqual(response.status_code, 200)

        payload = response.json()
        self.assertIn("header", payload)
        self.assertIn("teams", payload)
        self.assertIn("lineups", payload)
        self.assertIn("events", payload)
        self.assertIn("form", payload)
        self.assertIn("prediction", payload)
        self.assertIn("squads", payload)
        self.assertIn("partial_failures", payload)

        self.assertEqual(payload["header"]["match_id"], 5000)
        self.assertEqual(payload["teams"]["home"]["name"], "Home FC")
        self.assertEqual(payload["teams"]["away"]["name"], "Away FC")
        self.assertLessEqual(len(payload["form"]["home_last_five"]), 5)
        self.assertLessEqual(len(payload["form"]["away_last_five"]), 5)

        event_types = {event["event_type"] for event in payload["events"]}
        self.assertIn("goal", event_types)
        self.assertIn("card", event_types)
        self.assertEqual(len(payload["lineups"]["substitutions"]), 1)

        first_home_player = payload["squads"]["home"][0]
        self.assertIn("id", first_home_player)
        self.assertIn("name", first_home_player)
        self.assertIn("position", first_home_player)

    def test_match_experience_rejects_out_of_scope_competitions(self):
        response = self.client.get("/api/v1/match/9990/experience")
        self.assertEqual(response.status_code, 403)


if __name__ == "__main__":
    unittest.main()
