/**
 * Fantasy Roster Validation (/fantasy) — Cypress E2E Tests
 *
 * Tests the budget constraint logic from src/lib/fantasyValidation.ts.
 * Mocks a scenario where a user attempts to add a player that exceeds
 * the salary cap (100.00). Verifies the UI prevents the addition and
 * displays the correct warning.
 */

const SUPABASE_TOKEN_URL = "**/auth/v1/token?grant_type=password";
const API = "http://localhost:8000/api/v1";

// Fake authenticated session so the page doesn't redirect to /login
const MOCK_SESSION = {
  access_token: "mock-fantasy-token",
  token_type: "bearer",
  expires_in: 3600,
  expires_at: Math.floor(Date.now() / 1000) + 3600,
  refresh_token: "mock-refresh",
  user: {
    id: "user-uuid-fantasy",
    aud: "authenticated",
    role: "authenticated",
    email: "fantasy@terraball.dev",
    email_confirmed_at: "2024-01-01T00:00:00Z",
    created_at: "2024-01-01T00:00:00Z",
    updated_at: "2024-01-01T00:00:00Z",
    app_metadata: { provider: "email" },
    user_metadata: {},
  },
};

const MOCK_USER_PROFILE = {
  id: "user-uuid-fantasy",
  email: "fantasy@terraball.dev",
  username: "fantasy_tester",
};

// A player pool where the first 14 players cost 7.0 each (total = 98.0)
// and the 15th player costs 3.0 (would push total to 101.0 > 100 cap)
function buildPlayerPool() {
  const positions = ["GK", "GK", "DEF", "DEF", "DEF", "DEF", "DEF", "MID", "MID", "MID", "MID", "MID", "FWD", "FWD", "FWD"];
  return positions.map((pos, i) => ({
    player_id: i + 1,
    player_name: `Player ${i + 1}`,
    position_key: pos,
    team_id: i + 1, // all different teams
    team_name: `Team ${i + 1}`,
    team_logo: null,
    league_id: 1,
    league_name: "Test League",
    price: i < 14 ? 7.0 : 3.0, // 14 × 7 = 98; adding the 15th (3.0) = 101 > 100
    goals_season: 5,
    assists_season: 3,
    rating_season: 7.2,
    minutes_played: 1800,
  }));
}

// A squad that already has 14 players selected (total spent = 98.0)
function buildExistingSquad() {
  const pool = buildPlayerPool();
  return pool.slice(0, 14).map((p) => ({
    player_id: p.player_id,
    position_key: p.position_key,
    team_id: p.team_id,
    price: p.price,
  }));
}

describe("Fantasy Page — Budget Constraint Validation", () => {
  beforeEach(() => {
    // Stub Supabase auth so the user appears logged in
    cy.intercept("GET", "**/auth/v1/user", {
      statusCode: 200,
      body: MOCK_SESSION.user,
    }).as("getUser");

    cy.intercept("POST", SUPABASE_TOKEN_URL, {
      statusCode: 200,
      body: MOCK_SESSION,
    });

    // Supabase getSession — return a valid session
    cy.intercept("GET", "**/auth/v1/session", {
      statusCode: 200,
      body: MOCK_SESSION,
    });

    // Backend /auth/me
    cy.intercept("GET", `${API}/auth/me`, {
      statusCode: 200,
      body: MOCK_USER_PROFILE,
    }).as("fetchMe");

    // Fantasy rules
    cy.intercept("GET", `${API}/fantasy/player-mode/rules`, {
      statusCode: 200,
      body: {
        squad_size: 15,
        budget_cap: 100,
        position_limits: { GK: 2, DEF: 5, MID: 5, FWD: 3 },
        starting_limits: { GK: { min: 1, max: 1 }, DEF: { min: 3, max: 5 }, MID: { min: 2, max: 5 }, FWD: { min: 1, max: 3 } },
        free_transfers_per_matchday: 1,
        extra_transfer_penalty: 4,
        scoring_rules: {},
      },
    }).as("rules");

    // Player pool
    cy.intercept("GET", `${API}/fantasy/player-mode/players*`, {
      statusCode: 200,
      body: buildPlayerPool(),
    }).as("pool");

    // Existing squad — user already has 14 players (98.0 spent)
    cy.intercept("GET", `${API}/fantasy/player-mode/squad`, {
      statusCode: 200,
      body: {
        players: buildPlayerPool()
          .slice(0, 14)
          .map((p) => ({
            player_id: p.player_id,
            player_name: p.player_name,
            position_key: p.position_key,
            team_id: p.team_id,
            team_name: p.team_name,
            team_logo: null,
            purchase_price: p.price,
          })),
      },
    }).as("squad");

    // Matchday picks — empty (not relevant for this test)
    cy.intercept("GET", `${API}/fantasy/player-mode/matchday/*/picks`, {
      statusCode: 200,
      body: { picks: [] },
    });
  });

  it("prevents adding a player that would exceed the salary cap and shows a budget warning", () => {
    cy.visit("/fantasy");

    // Wait for data to load
    cy.wait(["@rules", "@pool", "@squad"]);

    // The Squad Builder tab should be active by default
    cy.contains("Squad Builder").should("exist");

    // Verify current budget state: 98.00 spent out of 100
    cy.contains("98.00").should("exist");

    // Find the 15th player (Player 15, costs 3.0) in the pool table and click "Add"
    cy.contains("tr", "Player 15").within(() => {
      cy.contains("button", "Add").click();
    });

    // Now attempt to save the squad — the zod validation should fire
    // because 98 + 3 = 101 > 100 budget cap
    cy.contains("button", "Save Squad").click();

    // The form validation error should display the budget exceeded message
    // from fantasyValidation.ts: "Budget exceeded. Spent 101.00 / 100.00."
    cy.contains("Budget exceeded").should("be.visible");
  });
});
