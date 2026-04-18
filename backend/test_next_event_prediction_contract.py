import unittest
from datetime import datetime, timedelta

from fastapi import FastAPI
from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

try:
    from backend.database import Base, get_db
    from backend.models import League, Match, MatchEvent, Player, Team
    from backend.routers.api import router as api_router
except ImportError:
    from database import Base, get_db
    from models import League, Match, MatchEvent, Player, Team
    from routers.api import router as api_router


class NextEventPredictionContractTests(unittest.TestCase):
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
        self._seed_supported_match()
        self._seed_out_of_scope_match()

    def _seed_supported_match(self):
        db = self.SessionLocal()
        try:
            db.add(League(id=39, name="Premier League", country="England", logo_url="pl"))

            home = Team(id=4101, name="Home Attackers", logo_url="home", stadium="Home", league_id=39)
            away = Team(id=4102, name="Away Creators", logo_url="away", stadium="Away", league_id=39)
            db.add_all([home, away])

            kickoff = datetime.utcnow() - timedelta(hours=1)
            match = Match(
                id=7000,
                home_team_id=home.id,
                away_team_id=away.id,
                start_time=kickoff,
                status="LIVE",
                home_score=1,
                away_score=1,
            )
            db.add(match)

            players = []
            for idx in range(1, 15):
                players.append(
                    Player(
                        id=5000 + idx,
                        name=f"Home Player {idx}",
                        position="Attacker" if idx <= 4 else "Midfielder",
                        team_id=home.id,
                        goals_season=max(0, 12 - idx),
                        assists_season=max(0, idx - 2),
                        rating_season=6.8 + (idx * 0.03),
                        minutes_played=600 + (idx * 120),
                    )
                )
            for idx in range(1, 15):
                players.append(
                    Player(
                        id=6000 + idx,
                        name=f"Away Player {idx}",
                        position="Midfielder" if idx <= 6 else "Defender",
                        team_id=away.id,
                        goals_season=max(0, 10 - idx),
                        assists_season=max(0, idx - 3),
                        rating_season=6.7 + (idx * 0.025),
                        minutes_played=650 + (idx * 110),
                    )
                )
            db.add_all(players)

            db.add_all(
                [
                    MatchEvent(
                        id=7101,
                        match_id=match.id,
                        minute=11,
                        event_type="Goal",
                        team_id=home.id,
                        player_name="Home Player 1",
                        detail="Open play assist: Home Player 3",
                    ),
                    MatchEvent(
                        id=7102,
                        match_id=match.id,
                        minute=28,
                        event_type="Card",
                        team_id=away.id,
                        player_name="Away Player 4",
                        detail="Yellow Card",
                    ),
                    MatchEvent(
                        id=7103,
                        match_id=match.id,
                        minute=39,
                        event_type="Goal",
                        team_id=away.id,
                        player_name="Away Player 2",
                        detail="Counter attack assist: Away Player 6",
                    ),
                    MatchEvent(
                        id=7104,
                        match_id=match.id,
                        minute=46,
                        event_type="Subst",
                        team_id=home.id,
                        player_name="Home Player 12",
                        detail="Home Player 12 in for Home Player 8",
                    ),
                ]
            )

            db.commit()
        finally:
            db.close()

    def _seed_out_of_scope_match(self):
        db = self.SessionLocal()
        try:
            db.add(League(id=9999, name="MLS", country="USA", logo_url=""))

            home = Team(id=9101, name="MLS Home", logo_url=None, stadium="M1", league_id=9999)
            away = Team(id=9102, name="MLS Away", logo_url=None, stadium="M2", league_id=9999)
            db.add_all([home, away])

            match = Match(
                id=7999,
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

    def test_next_event_prediction_contract(self):
        response = self.client.get("/api/v1/match/7000/next-events/prediction?minute=55")
        self.assertEqual(response.status_code, 200)

        payload = response.json()
        self.assertEqual(payload["match_id"], 7000)
        self.assertIn("next_goal", payload)
        self.assertIn("next_assist", payload)

        for key in ("next_goal", "next_assist"):
            section = payload[key]
            self.assertIn("top_candidates", section)
            self.assertLessEqual(len(section["top_candidates"]), 3)
            self.assertGreater(len(section["top_candidates"]), 0)

            self.assertIn(section["confidence_label"], {"low", "medium", "high"})

            probs = [candidate["probability"] for candidate in section["top_candidates"]]
            self.assertAlmostEqual(sum(probs), 1.0, places=5)

    def test_next_event_prediction_scope_guard(self):
        response = self.client.get("/api/v1/match/7999/next-events/prediction")
        self.assertEqual(response.status_code, 403)


if __name__ == "__main__":
    unittest.main()
