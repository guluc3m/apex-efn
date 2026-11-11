import { defineConfig } from '@playwright/test'

// Browser specs mint their own Auth.js session cookie with this secret (e2e/session.ts), so no
// Keycloak is needed; API calls are answered by MSW in the page.
export const AUTH_SECRET = 'e2e-only-secret-not-used-anywhere-else'

export default defineConfig({
  testDir: 'e2e',
  webServer: {
    command: 'pnpm exec next dev -p 3100',
    url: 'http://localhost:3100',
    reuseExistingServer: false,
    timeout: 120_000,
    env: {
      AUTH_SECRET,
      AUTH_KEYCLOAK_ID: 'e2e',
      AUTH_KEYCLOAK_SECRET: 'e2e',
      AUTH_KEYCLOAK_ISSUER: 'http://localhost:9/realms/e2e',
      NEXT_PUBLIC_API_MOCKING: 'enabled',
    },
  },
  use: { baseURL: 'http://localhost:3100' },
})
