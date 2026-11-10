/**
 * Opt-in smoke test for the real driver: `BROWSER_WORKER_REAL_BROWSER=1 pnpm --filter @apex/browser-worker test`.
 *
 * Off by default because CI images without a Chrome build would fail for an environment reason, not a code one.
 * The pool logic is covered with fakes in ``pool.test.ts``; this test only proves the wiring to Puppeteer.
 */

import { describe, expect, it } from 'vitest'

import { createPuppeteerDriver } from './puppeteer-driver.js'

const enabled = process.env.BROWSER_WORKER_REAL_BROWSER === '1'

describe.skipIf(!enabled)('createPuppeteerDriver', () => {
  it(
    'launches Chrome, opens and closes a page, and reports memory',
    async () => {
      const driver = createPuppeteerDriver({ headless: true })
      const handle = await driver.launch({ proxyUrl: null })
      try {
        expect(handle.isConnected()).toBe(true)

        const page = await handle.newPage()
        expect(page.id).toContain(handle.id)
        await page.close()

        expect(handle.memoryMb()).toBeGreaterThan(0)
      } finally {
        await handle.close()
      }

      expect(handle.isConnected()).toBe(false)
    },
    60_000
  )
})
