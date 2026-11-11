import { expect, test, type Page } from '@playwright/test'

import { signInAs } from './session'

// D6-08. Flows from spec 5.11. Those that run here are driven through the real UI; the API is
// answered by MSW (default) or by explicit network stubs where a specific status is the point.
// Flows that need a backend which does not exist in this suite are test.fixme, never faked.
test.skip(!process.env.E2E_BROWSER && !process.env.GITHUB_ACTIONS, 'set E2E_BROWSER=1 to run')

test.beforeEach(async ({ context }) => signInAs(context))

async function requestMission(page: Page) {
  await page.goto('/es/misiones/nueva')
  await page.getByLabel('País de entrega').fill('ES')
  await page.getByPlaceholder('Describe lo que necesitas').fill('Botellas PET de 500 ml con tapón flip-top')
  await page.getByRole('button', { name: 'Enviar' }).click()
}

test('mission: natural-language request, review and launch lands on the mission', async ({ page }) => {
  await requestMission(page)
  await expect(page.getByLabel('Producto')).toHaveValue('PET bottle 500 ml with flip-top cap')
  await page.getByRole('button', { name: 'Lanzar misión' }).click()
  await expect(page).toHaveURL(/\/es\/misiones\/ms_mock_1$/)
})

// Network stubs need the page's own requests, so MSW's service worker is blocked here.
test.describe('API statuses', () => {
  test.use({ serviceWorkers: 'block' })

  const problem = (body: Record<string, unknown>) => ({
    status: body.status as number,
    contentType: 'application/problem+json',
    body: JSON.stringify({ type: 'about:blank', ...body }),
  })

  async function stubAndLaunch(page: Page, missionResponse: ReturnType<typeof problem>) {
    await page.route('**/api/v1/sourcing-requests', (r) =>
      r.fulfill({
        status: 201,
        json: {
          id: 'sr_1',
          status: 'normalized',
          spec: { description: 'PET bottle' },
          quantity_tiers: [{ quantity: 5000, priority: 'primary' }],
          delivery_country: 'ES',
          needs_clarification: [],
          created_at: '2026-11-09T09:00:00Z',
        },
      }),
    )
    await page.route('**/api/v1/missions', (r) => r.fulfill(missionResponse))
    await requestMission(page)
    await page.getByRole('button', { name: 'Lanzar misión' }).click()
  }

  test('launch without an active financial snapshot is blocked and points to the CSV import (criterion 1)', async ({ page }) => {
    await stubAndLaunch(page, problem({ title: 'Conflict', status: 409, detail: 'No active financial snapshot' }))
    await expect(page.getByText('El snapshot financiero no está activo')).toBeVisible()
    await expect(page.getByRole('link', { name: 'Importar CSV financiero' })).toBeVisible()
  })

  test('428 reauth_required sends the user to the step-up and never signs silently', async ({ page }) => {
    // Keycloak is not part of this suite: the redirect target is answered locally.
    await page.route('**/api/auth/signin**', (r) => r.fulfill({ status: 200, contentType: 'text/html', body: 'step-up' }))
    await stubAndLaunch(
      page,
      problem({ title: 'Reauth', status: 428, error: 'reauth_required', reason: 'session_expired' }),
    )
    await page.waitForURL(/\/api\/auth\/signin\?.*stepUp=1/)
  })
})

// Each needs a backend (or MSW handlers) that does not exist yet. Tracked on #79.
test.fixme('onboarding with CSV: upload, import report, signed activation (needs financial-csv endpoints and a signing session)', () => {})
test.fixme('gate from an anomalous price (needs orchestrator gate queue and offers data)', () => {})
test.fixme('gate from a low-confidence seller (needs orchestrator gate queue and offers data)', () => {})
test.fixme('negotiation against the mock chat with approve-send (needs orchestrator, browser worker and mock marketplace in compose)', () => {})
test.fixme('dashboard: deals, filters and actions (needs deals endpoints)', () => {})
test.fixme('open a signing session (needs Keycloak step-up and the passkey ceremony)', () => {})
test.fixme('several signatures inside the window (needs a signing session and the decisions API)', () => {})
test.fixme('window expiry with an injected clock turns the panel read-only (needs an open signing session)', () => {})
