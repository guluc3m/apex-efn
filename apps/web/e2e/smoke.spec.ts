import { expect, test } from '@playwright/test'

// The app routes require a session (D1-05). This spec was written before authentication landed
// (D6-03a), when `/es/decisiones` rendered the shell publicly. It now asserts the current contract:
// an anonymous visitor is sent to the sign-in flow, which in turn redirects to Keycloak.
//
// It uses Playwright's `request` fixture (no browser), so `pnpm ci:local` can run it on a developer
// machine without Chromium's system libraries. DEV-6 owns the browser-driven suite (D6-08).
test('an unauthenticated app route sends the visitor to the sign-in flow', async ({ request }) => {
  const response = await request.get('/es/decisiones', { maxRedirects: 0 })

  expect(response.status()).toBe(307)
  expect(response.headers()['location']).toContain('/api/auth/signin')
})

test('the public landing renders without a session', async ({ request }) => {
  const response = await request.get('/es')

  expect(response.status()).toBe(200)
  expect(await response.text()).toContain('APEX-EFN')
})
