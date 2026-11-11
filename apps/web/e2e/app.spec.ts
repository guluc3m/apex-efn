import { expect, test } from '@playwright/test'

import { signInAs } from './session'

// Browser-driven; needs Chromium's system libraries, so it only runs where the e2e job says so
// (GitHub runners) or when E2E_BROWSER=1. The full-stack flows (CSV onboarding, gate, negotiation,
// window expiry) need the compose stack and come in a follow-up.
test.skip(!process.env.E2E_BROWSER && !process.env.GITHUB_ACTIONS, 'set E2E_BROWSER=1 to run')

test.beforeEach(async ({ context }) => signInAs(context))

const screens = [
  { path: '/es/misiones', heading: 'Misiones' },
  { path: '/es/decisiones/gate', heading: /Cola de gate/ },
  { path: '/es/misiones/nueva', heading: /misión/i },
]

for (const { path, heading } of screens) {
  test(`${path} renders for a signed-in buyer`, async ({ page }) => {
    await page.goto(path)
    await expect(page.getByRole('heading', { name: heading }).first()).toBeVisible()
  })
}

test('English routes render English messages', async ({ page }) => {
  await page.goto('/en/misiones')
  await expect(page.getByRole('heading', { name: 'Missions' }).first()).toBeVisible()
})
