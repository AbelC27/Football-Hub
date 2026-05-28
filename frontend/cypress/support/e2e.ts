// Cypress E2E support file
// Add custom commands or global configuration here

// Prevent uncaught exceptions from failing tests (Next.js hydration noise)
Cypress.on("uncaught:exception", () => false);
