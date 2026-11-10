import { describe, expect, it } from 'vitest'

import { WorkerError } from '../errors.js'

import type { BrowserDriver, BrowserHandle, BrowserPage, LaunchOptions } from './driver.js'
import { BrowserPool, type PoolOptions } from './pool.js'

class FakePage implements BrowserPage {
  closed = false
  constructor(readonly id: string) {}

  close(): Promise<void> {
    this.closed = true
    return Promise.resolve()
  }
}

class FakeBrowser implements BrowserHandle {
  readonly pages: FakePage[] = []
  closed = false
  connected = true
  memory: number | null = null

  constructor(readonly id: string) {}

  newPage(): Promise<BrowserPage> {
    const page = new FakePage(`${this.id}:page-${this.pages.length + 1}`)
    this.pages.push(page)
    return Promise.resolve(page)
  }

  close(): Promise<void> {
    this.closed = true
    this.connected = false
    return Promise.resolve()
  }

  memoryMb(): number | null {
    return this.memory
  }

  isConnected(): boolean {
    return this.connected
  }
}

class FakeDriver implements BrowserDriver {
  readonly browsers: FakeBrowser[] = []
  readonly launches: LaunchOptions[] = []
  failNext = false

  launch(options: LaunchOptions): Promise<BrowserHandle> {
    if (this.failNext) {
      this.failNext = false
      return Promise.reject(new Error('launch exploded'))
    }
    this.launches.push(options)
    const browser = new FakeBrowser(`browser-${this.browsers.length + 1}`)
    this.browsers.push(browser)
    return Promise.resolve(browser)
  }
}

function testClock(): { now: () => Date; advance: (ms: number) => void } {
  let millis = 1_000_000
  return {
    now: () => new Date(millis),
    advance: (ms: number) => {
      millis += ms
    },
  }
}

function makePool(options: Partial<PoolOptions> = {}): { pool: BrowserPool; driver: FakeDriver; clock: ReturnType<typeof testClock> } {
  const driver = new FakeDriver()
  const clock = testClock()
  return {
    driver,
    clock,
    pool: new BrowserPool({
      maxBrowsers: 2,
      maxPagesPerBrowser: 50,
      maxMemoryMbPerBrowser: 1024,
      acquireTimeoutMs: 1_000,
      idleTimeoutMs: 60_000,
      clock,
      driver,
      ...options,
    }),
  }
}

describe('BrowserPool', () => {
  it('reuses one browser for several pages and reports them', async () => {
    const { pool, driver } = makePool()
    const a = await pool.acquire('acct-1')
    const b = await pool.acquire('acct-1')

    expect(driver.browsers).toHaveLength(1)
    expect(a.browserId).toBe(b.browserId)
    expect(pool.stats()).toMatchObject({ browsers: 1, pages: 2, launched: 1 })

    await a.release()
    await b.release()
    expect(pool.stats().pages).toBe(0)
    expect(driver.browsers[0]?.closed).toBe(false) // the browser stays warm
  })

  it('closes the page on release and is idempotent', async () => {
    const { pool, driver } = makePool()
    const lease = await pool.acquire(null)
    const page = driver.browsers[0]?.pages[0]

    await lease.release()
    await lease.release()

    expect(page?.closed).toBe(true)
    expect(pool.stats().pages).toBe(0)
  })

  it('waits for a retired browser to close before launching its replacement', async () => {
    const { pool } = makePool({ maxBrowsers: 1, maxPagesPerBrowser: 1 })
    const first = await pool.acquire('a')
    await pool.sweep() // budget reached while the page is still open: the browser is retiring

    let second: Awaited<ReturnType<BrowserPool['acquire']>> | undefined
    const waiting = pool.acquire('b').then((lease) => {
      second = lease
    })
    await new Promise((resolve) => setTimeout(resolve, 10))
    expect(second).toBeUndefined()
    expect(pool.stats().waiting).toBe(1)

    await first.release() // closes the retired browser and wakes the waiter
    await waiting

    expect(second?.browserId).toBe('browser-2')
    expect(pool.stats().waiting).toBe(0)
  })

  it('answers timeout when no browser frees up in time', async () => {
    const { pool } = makePool({ maxBrowsers: 1, maxPagesPerBrowser: 1, acquireTimeoutMs: 20 })
    const first = await pool.acquire('a')
    await pool.sweep()

    await expect(pool.acquire('b')).rejects.toMatchObject({
      code: 'timeout',
      retryable: true,
    } satisfies Partial<WorkerError>)

    await first.release()
  })

  it('recycles a browser that served its page budget, once its pages come back', async () => {
    const { pool, driver } = makePool({ maxPagesPerBrowser: 2 })
    const a = await pool.acquire('a')
    const b = await pool.acquire('a')
    await a.release()

    await pool.sweep() // budget reached, but b is still open: the browser must not be killed mid-page
    expect(driver.browsers[0]?.closed).toBe(false)

    await b.release()
    expect(driver.browsers[0]?.closed).toBe(true)

    const next = await pool.acquire('a')
    expect(next.browserId).toBe('browser-2')
    expect(pool.stats().recycled).toBe(1)
  })

  it('recycles a browser that grows past the memory limit', async () => {
    const { pool, driver } = makePool({ maxMemoryMbPerBrowser: 500 })
    const lease = await pool.acquire('a')
    const browser = driver.browsers[0]
    if (browser !== undefined) {
      browser.memory = 900
    }

    await pool.sweep()
    expect(browser?.closed).toBe(false) // one page still open
    await lease.release()
    expect(browser?.closed).toBe(true)
    expect(pool.stats().recycled).toBe(1)
  })

  it('does not apply the memory rule when it is disabled', async () => {
    const { pool, driver } = makePool({ maxMemoryMbPerBrowser: 0 })
    const lease = await pool.acquire('a')
    const browser = driver.browsers[0]
    if (browser !== undefined) {
      browser.memory = 99_999
    }
    await pool.sweep()
    await lease.release()
    expect(browser?.closed).toBe(false)
  })

  it('keeps the last browser warm when it goes idle', async () => {
    const { pool, driver, clock } = makePool()
    const lease = await pool.acquire('a')
    await lease.release()

    clock.advance(61_000)
    await pool.sweep()

    expect(driver.browsers[0]?.closed).toBe(false)
    expect(pool.stats().browsers).toBe(1)
  })

  it('drops a disconnected browser and launches a fresh one', async () => {
    const { pool, driver } = makePool({ maxBrowsers: 1 })
    const lease = await pool.acquire('a')
    const browser = driver.browsers[0]
    if (browser !== undefined) {
      browser.connected = false
    }
    await lease.release()

    await pool.sweep()
    expect(browser?.closed).toBe(true)

    const next = await pool.acquire('a')
    expect(next.browserId).toBe('browser-2')
  })

  it('releases the page when the task throws', async () => {
    const { pool, driver } = makePool()
    await expect(
      pool.run('a', () => Promise.reject(new Error('adapter failed')))
    ).rejects.toThrow('adapter failed')

    expect(pool.stats().pages).toBe(0)
    expect(driver.browsers[0]?.pages[0]?.closed).toBe(true)
  })

  it('passes the proxy of the account to the launch', async () => {
    const { pool, driver } = makePool({ proxyFor: (accountId) => (accountId === 'paid' ? 'http://proxy' : null) })
    const lease = await pool.acquire('paid')
    await lease.release()
    expect(driver.launches).toEqual([{ proxyUrl: 'http://proxy' }])
  })

  it('propagates a launch failure instead of inventing a timeout', async () => {
    const { pool, driver } = makePool({ acquireTimeoutMs: 1_000 })
    driver.failNext = true
    await expect(pool.acquire('a')).rejects.toThrow('launch exploded')
    expect(pool.stats().browsers).toBe(0)
  })

  it('closes every browser and refuses new leases after close', async () => {
    const { pool, driver } = makePool()
    await (await pool.acquire('a')).release()
    await pool.close()

    expect(driver.browsers[0]?.closed).toBe(true)
    await expect(pool.acquire('a')).rejects.toMatchObject({ code: 'internal' })
  })
})
