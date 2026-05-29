/**
 * Fantasy Roster Validation (/fantasy) — Cypress E2E Tests
 *
 * Tests the budget constraint logic from src/lib/fantasyValidation.ts.
 * Mocks a scenario where a user attempts to add a player that exceeds
 * the salary cap (100.00). Verifies the UI prevents the addition and
 * displays the correct warning.
 *
 * Strategy: Log in via the /login page (intercepting Supabase token grant)
 * so the Supabase client holds a valid in-memory session, then navigate
 * to /fantasy with all API endpoints mocked.
 */

const API = "http://localhost:8000/api/v1";
const SUPABASE_TOKEN_URL = "**/auth/v1/token?grant_type=password";

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

function buildPlayerPool() {
  const positions = [
    "GK", "GK", "DEF", "DEF", "DEF", "DEF", "DEF",
    "MID", "MID", "MID", "MID", "MID", "FWD", "FWD", "FWD",
  ];
  return positions.map((pos, i) => ({
    player_id: i + 1,
    player_name: `Player ${i + 1}`,
    position_key: pos,
    team_id: i + 1,
    team_name: `Team ${i + 1}`,
    team_logo: null,
    league_id: 1,
    league_name: "Test League",
    price: i < 14 ? 7.0 : 3.0,
    goals_season: 5,
    assists_season: 3,
    rating_season: 7.2,
    minutes_played: 1800,
  }));
}

describe("Fantasy Page — Budget Constraint Validation", () => {
  beforeEach(() => {
    // --- Auth intercepts ---
    cy.intercept("POST", SUPABASE_TOKEN_URL, {
      statusCode: 200,
      body: MOCK_SESSION,
    }).as("signIn");

    cy.intercept("GET", "**/auth/v1/user", {
      statusCode: 200,
      body: MOCK_SESSION.user,
    });

    cy.intercept("GET", `${API}/auth/me`, {
      statusCode: 200,
      body: MOCK_USER_PROFILE,
    }).as("fetchMe");

    // --- Fantasy API intercepts ---
    cy.intercept("GET", `${API}/fantasy/player-mode/rules`, {
      statusCode: 200,
      body: {
        squad_size: 15,
        budget_cap: 100,
        position_limits: { GK: 2, DEF: 5, MID: 5, FWD: 3 },
        starting_limits: {
          GK: { min: 1, max: 1 },
          DEF: { min: 3, max: 5 },
          MID: { min: 2, max: 5 },
          FWD: { min: 1, max: 3 },
        },
        free_transfers_per_matchday: 1,
        extra_transfer_penalty: 4,
        scoring_rules: {},
      },
    }).as("rules");

    cy.intercept("GET", `${API}/fantasy/player-mode/players*`, {
      statusCode: 200,
      body: buildPlayerPool(),
    }).as("pool");

    // Existing squad: 14 players at 7.0 each = 98.0 spent
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

    cy.intercept("GET", `${API}/fantasy/player-mode/matchday/*/picks`, {
      statusCode: 200,
      body: { picks: [] },
    });

    // --- Log in first to establish Supabase session ---
    cy.visit("/login");
    cy.get('input[name="email"]').type("fantasy@terraball.dev");
    cy.get('input[name="password"]').type("TestPass123!");
    cy.get('button[type="submit"]').click();
    cy.wait("@signIn");

    // Navigate to fantasy page
    cy.visit("/fantasy");
    cy.contains("Fantasy Manager", { timeout: 10000 }).should("be.visible");
  });

  it("prevents adding a player that would exceed the salary cap and shows a budget warning", () => {
    // Verify the Squad Builder tab is active and budget shows 98.00
    cy.contains("Squad Builder").should("exist");
    cy.contains("98.00").should("exist");

    // The "Budget Left" card should show "In range" initially (100 - 98 = 2.00)
    cy.contains("In range").should("exist");

    // Add Player 15 (costs 3.0) — this pushes total to 101.0 > 100 cap
    cy.contains("tr", "Player 15").within(() => {
      cy.contains("button", "Add").click();
    });

    // After adding, the budget card updates reactively:
    // Budget Spent becomes 101.00, Budget Left becomes -1.00 with "Over budget"
    cy.contains("Over budget").should("be.visible");
    cy.contains("101.00").should("exist");

    // Click Save Squad — the zod validation fires and shows a toast error
    cy.contains("button", "Save Squad").click();

    // The sonner toast renders with the validation failure message.
    // The toast contains either the specific "Budget exceeded" message
    // (if zodResolver maps it to selected_players) or the fallback
    // "Squad validation failed" message.
    cy.get('[data-sonner-toast]', { timeout: 5000 })
      .should("be.visible")
      .and("contain.text", "validation failed");
  });
});
