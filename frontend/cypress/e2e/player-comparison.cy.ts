/**
 * Player Comparison (/compare/players/[id1]/vs/[id2]) — Cypress E2E Tests
 *
 * Tests the rendering of the comparison view by mocking the backend
 * response for two distinct players. Verifies the page loads the mocked
 * data and that the PlayerComparisonRadar component mounts.
 */

const API = "http://localhost:8000/api/v1";

const MOCK_PLAYER_1 = {
  id: 42,
  name: "Erling Haaland",
  position: "Forward",
  nationality: "Norway",
  age: 24,
  photo_url: null,
  team: { id: 10, name: "Manchester City", logo_url: null },
  league: { id: 1, name: "Premier League" },
  stats: {
    goals: 18,
    assists: 4,
    minutes: 2100,
    rating: 8.1,
    yellow_cards: 2,
    red_cards: 0,
    goal_involvements: 22,
    overall_rating: 91,
  },
  overall_score: {
    value: 82.5,
    components: [
      { key: "rating", label: "Season Rating", weight: 30, contribution: 24.3, available: true },
      { key: "goals", label: "Goals", weight: 25, contribution: 22.5, available: true },
      { key: "assists", label: "Assists", weight: 15, contribution: 5.0, available: true },
      { key: "minutes", label: "Minutes", weight: 10, contribution: 7.0, available: true },
      { key: "discipline", label: "Discipline", weight: 10, contribution: 9.4, available: true },
      { key: "form", label: "Form", weight: 10, contribution: 8.0, available: true },
    ],
  },
  recent_form: [
    { match_id: 101, opponent_name: "Arsenal", result: "W" },
    { match_id: 102, opponent_name: "Liverpool", result: "D" },
    { match_id: 103, opponent_name: "Chelsea", result: "W" },
    { match_id: 104, opponent_name: "Tottenham", result: "W" },
    { match_id: 105, opponent_name: "Aston Villa", result: "L" },
  ],
};

const MOCK_PLAYER_2 = {
  id: 77,
  name: "Kylian Mbappé",
  position: "Forward",
  nationality: "France",
  age: 25,
  photo_url: null,
  team: { id: 20, name: "Real Madrid", logo_url: null },
  league: { id: 2, name: "La Liga" },
  stats: {
    goals: 15,
    assists: 8,
    minutes: 2400,
    rating: 7.9,
    yellow_cards: 3,
    red_cards: 0,
    goal_involvements: 23,
    overall_rating: 89,
  },
  overall_score: {
    value: 78.2,
    components: [
      { key: "rating", label: "Season Rating", weight: 30, contribution: 23.7, available: true },
      { key: "goals", label: "Goals", weight: 25, contribution: 18.75, available: true },
      { key: "assists", label: "Assists", weight: 15, contribution: 10.0, available: true },
      { key: "minutes", label: "Minutes", weight: 10, contribution: 8.0, available: true },
      { key: "discipline", label: "Discipline", weight: 10, contribution: 9.1, available: true },
      { key: "form", label: "Form", weight: 10, contribution: 6.0, available: true },
    ],
  },
  recent_form: [
    { match_id: 201, opponent_name: "Barcelona", result: "W" },
    { match_id: 202, opponent_name: "Atletico", result: "W" },
    { match_id: 203, opponent_name: "Sevilla", result: "D" },
    { match_id: 204, opponent_name: "Valencia", result: "L" },
    { match_id: 205, opponent_name: "Villarreal", result: "W" },
  ],
};

const MOCK_COMPARISON_RESPONSE = {
  player1: MOCK_PLAYER_1,
  player2: MOCK_PLAYER_2,
  comparison: {
    metric_deltas: {
      goals: 3,
      assists: -4,
      rating: 0.2,
      minutes: -300,
      goal_involvements: -1,
      overall_rating: 2,
      overall_score: 4.3,
    },
    score_winner_id: 42,
    scope: "season",
    fallback_active: false,
  },
  score_formula: "weighted_sum",
  note: null,
};

describe("Player Comparison — /compare/players/42/vs/77", () => {
  beforeEach(() => {
    // Stub Supabase auth (comparison page doesn't require auth, but
    // the AuthProvider still fires a session check on mount)
    cy.intercept("GET", "**/auth/v1/user", {
      statusCode: 401,
      body: { message: "not authenticated" },
    });

    // Mock the player comparison API endpoint
    cy.intercept("GET", `${API}/players/42/vs/77`, {
      statusCode: 200,
      body: MOCK_COMPARISON_RESPONSE,
    }).as("comparison");
  });

  it("renders both player cards with mocked data", () => {
    cy.visit("/compare/players/42/vs/77");

    cy.wait("@comparison");

    // Verify both player names appear
    cy.contains("Erling Haaland").should("be.visible");
    cy.contains("Kylian Mbappé").should("be.visible");

    // Verify the "VS" separator renders
    cy.contains("VS").should("exist");

    // Verify team names
    cy.contains("Manchester City").should("exist");
    cy.contains("Real Madrid").should("exist");

    // Verify season stats render for player 1
    cy.contains("18").should("exist"); // goals
    cy.contains("91").should("exist"); // overall rating

    // Verify season stats render for player 2
    cy.contains("15").should("exist"); // goals
    cy.contains("89").should("exist"); // overall rating
  });

  it("mounts the PlayerComparisonRadar component", () => {
    cy.visit("/compare/players/42/vs/77");

    cy.wait("@comparison");

    // The radar section has a heading "Performance Radar"
    cy.contains("Performance Radar").should("be.visible");

    // The @nivo/radar ResponsiveRadar renders an SVG inside the radar container
    // The container div has a fixed height class (h-[360px])
    cy.get("section")
      .contains("Performance Radar")
      .closest("section")
      .within(() => {
        // Nivo renders an SVG element for the radar chart
        cy.get("svg").should("exist");
      });
  });

  it("displays metric delta cards", () => {
    cy.visit("/compare/players/42/vs/77");

    cy.wait("@comparison");

    // Rating Delta card
    cy.contains("Rating Delta").should("exist");
    // Overall Score Delta card
    cy.contains("Overall Score Delta").should("exist");
    // Goals Delta
    cy.contains("Goals Delta").should("exist");
    // Assists Delta
    cy.contains("Assists Delta").should("exist");
  });
});
