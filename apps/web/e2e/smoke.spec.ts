import { expect, test } from '@playwright/test'

// TODO(D6-03, after D2-08/D1-05): virtual authenticator + injected clock specs for criteria 19-22.
test('the shell shows the signing indicator without a session', async ({ page }) => {
  const res = await page.goto('/es/decisiones')
  expect(res?.status()).toBeLessThan(500)
  await expect(page.getByText('Sin sesión')).toBeVisible()
})
