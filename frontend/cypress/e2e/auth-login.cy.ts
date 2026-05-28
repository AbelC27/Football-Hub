/**
 * Authentication (/login) — Cypress E2E Tests
 *
 * Intercepts the Supabase password-grant request
 * (POST to /auth/v1/token?grant_type=password) and tests both
 * the success and failure paths.
 */

const SUPABASE_TOKEN_URL = "**/auth/v1/token?grant_type=password";

const MOCK_SESSION = {
  access_token: "mock-access-token-abc123",
  token_type: "bearer",
  expires_in: 3600,
  expires_at: Math.floor(Date.now() / 1000) + 3600,
  refresh_token: "mock-refresh-token-xyz",
  user: {
    id: "a1b2c3d4-e5f6-7890-abcd-ef1234567890",
    aud: "authenticated",
    role: "authenticated",
    email: "test@terraball.dev",
    email_confirmed_at: "2024-01-01T00:00:00Z",
    created_at: "2024-01-01T00:00:00Z",
    updated_at: "2024-01-01T00:00:00Z",
    app_metadata: { provider: "email" },
    user_metadata: {},
  },
};

const MOCK_USER_PROFILE = {
  id: "a1b2c3d4-e5f6-7890-abcd-ef1234567890",
  email: "test@terraball.dev",
  username: "terraball_tester",
  favorite_team_id: null,
  favorite_player_id: null,
};

describe("Login Page — /login", () => {
  beforeEach(() => {
    // Stub the Supabase session check so the AuthProvider doesn't redirect
    cy.intercept("GET", "**/auth/v1/user", {
      statusCode: 401,
      body: { message: "not authenticated" },
    }).as("getUser");
  });

  describe("Success path", () => {
    it("logs in and redirects to the home page on valid credentials", () => {
      // Intercept Supabase password grant — return a valid session
      cy.intercept("POST", SUPABASE_TOKEN_URL, {
        statusCode: 200,
        body: MOCK_SESSION,
      }).as("signIn");

      // Intercept the backend /auth/me call that AuthContext makes after login
      cy.intercept("GET", "**/api/v1/auth/me", {
        statusCode: 200,
        body: MOCK_USER_PROFILE,
      }).as("fetchMe");

      cy.visit("/login");

      // Fill in the form
      cy.get('input[name="email"]').type("test@terraball.dev");
      cy.get('input[name="password"]').type("SecurePass123!");
      cy.get('button[type="submit"]').click();

      // Wait for the Supabase token request
      cy.wait("@signIn");

      // After successful login, the AuthContext calls login() which pushes to "/"
      cy.url().should("not.include", "/login");
    });
  });

  describe("Failure path", () => {
    it("displays an error message when Supabase returns 400", () => {
      // Intercept Supabase password grant — return an error
      cy.intercept("POST", SUPABASE_TOKEN_URL, {
        statusCode: 400,
        body: {
          error: "invalid_grant",
          error_description: "Invalid login credentials",
        },
      }).as("signInFail");

      cy.visit("/login");

      // Fill in the form with bad credentials
      cy.get('input[name="email"]').type("wrong@example.com");
      cy.get('input[name="password"]').type("badpassword");
      cy.get('button[type="submit"]').click();

      cy.wait("@signInFail");

      // The error banner should render with the Supabase error message
      cy.get(".bg-red-100")
        .should("be.visible")
        .and("contain.text", "Invalid login credentials");

      // User should remain on the login page
      cy.url().should("include", "/login");
    });
  });
});
