/**
 * Chromium pool (D5-02).
 *
 * One process per browser, pages handed out on lease. The pool bounds three things the worker cannot leave to
 * chance: how many Chrome processes run at once, how long a browser lives (pages served and resident memory) and
 * how long an idle browser stays up. A page always belongs to exactly one lease, and the lease is always released
 * through `run` or `release`, so a page leaked by an adapter cannot pin a browser forever.
 *
 * Time comes from the injected ``Clock`` for decisions and from real timers only to wake a waiter. The recycling
 * rules are pure functions of the pool state, so a test drives ``sweep()`` directly instead of waiting.
 */

import type { Clock } from '../clock.js'
import { WorkerError } from '../errors.js'

import type { BrowserDriver, BrowserHandle, BrowserPage } from './driver.js'

export interface PoolOptions {
  /** Chrome processes alive at the same time. */
  maxBrowsers: number
  /** Pages a browser serves before it is retired at the next idle moment. */
  maxPagesPerBrowser: number
  /** Resident memory that retires a browser. ``0`` disables the check (some drivers cannot measure it). */
  maxMemoryMbPerBrowser: number
  /** How long ``acquire`` waits for a free browser before answering ``timeout``. */
  acquireTimeoutMs: number
  /** How long a browser with no open pages stays alive. */
  idleTimeoutMs: number
  clock: Clock
  driver: BrowserDriver
  /** Proxy for an account, or ``null``. Resolved by the caller so credentials stay out of the pool. */
  proxyFor?: (accountId: string | null) => string | null
  /** Every launch, recycle and close, for metrics and logs. Never carries URLs or credentials. */
  onEvent?: (event: PoolEvent) => void
}

export interface PoolEvent {
  type: 'launched' | 'recycled' | 'closed'
  browserId: string
  reason?: 'pages' | 'memory' | 'idle' | 'disconnected' | 'shutdown'
}

export interface PageLease {
  readonly page: BrowserPage
  readonly browserId: string
  readonly accountId: string | null
  release(): Promise<void>
}

export interface PoolStats {
  browsers: number
  pages: number
  waiting: number
  launched: number
  recycled: number
}

interface Slot {
  handle: BrowserHandle
  openPages: number
  pagesServed: number
  lastUsedAt: number
  retireReason: PoolEvent['reason'] | null
}

export class BrowserPool {
  private readonly slots = new Set<Slot>()
  private readonly waiters = new Set<() => void>()
  private launching = 0
  private launched = 0
  private recycled = 0
  private closed = false

  constructor(private readonly options: PoolOptions) {}

  /** Opens a page for ``accountId`` and leases it. The caller must release it (``run`` does that for you). */
  async acquire(accountId: string | null = null): Promise<PageLease> {
    // The acquire deadline is wall-clock, not the injected clock: it bounds a real wait, while `clock` exists so
    // the recycling rules (idle time, page budget) stay deterministic in tests.
    const deadline = Date.now() + this.options.acquireTimeoutMs
    for (;;) {
      if (this.closed) {
        throw new WorkerError('internal', 503, { detail: 'browser pool is closed' })
      }
      const slot = this.pick()
      if (slot !== undefined) {
        return this.lease(slot, accountId)
      }
      if (this.slots.size + this.launching < this.options.maxBrowsers) {
        return this.launchAndLease(accountId, deadline)
      }
      const remaining = deadline - Date.now()
      if (remaining <= 0) {
        throw new WorkerError('timeout', 503, {
          detail: 'no browser became available before the acquire timeout',
          retryable: true,
          retryAfterSeconds: 1,
        })
      }
      await this.waitForSlot(remaining)
    }
  }

  /** Leases a page for the duration of ``task`` and always releases it, even when ``task`` throws. */
  async run<T>(accountId: string | null, task: (page: BrowserPage) => Promise<T>): Promise<T> {
    const lease = await this.acquire(accountId)
    try {
      return await task(lease.page)
    } finally {
      await lease.release()
    }
  }

  /**
   * Applies the recycling rules once. Called by the watchdog on a timer and directly by tests.
   *
   * A browser is retired when it has served its page budget or grown past the memory limit; it closes as soon as
   * its open pages come back, so a running page is never killed mid-request. Idle browsers close immediately, but
   * the last one is kept warm so the next job does not pay a launch.
   */
  async sweep(): Promise<void> {
    const now = this.options.clock.now().getTime()
    const closing: Promise<void>[] = []
    for (const slot of [...this.slots]) {
      if (!slot.handle.isConnected()) {
        this.markRetiring(slot, 'disconnected')
        closing.push(this.retire(slot))
        continue
      }
      if (slot.retireReason === null && slot.pagesServed >= this.options.maxPagesPerBrowser) {
        this.markRetiring(slot, 'pages')
      }
      const memory = slot.handle.memoryMb()
      if (
        slot.retireReason === null &&
        this.options.maxMemoryMbPerBrowser > 0 &&
        memory !== null &&
        memory > this.options.maxMemoryMbPerBrowser
      ) {
        this.markRetiring(slot, 'memory')
      }
      if (slot.retireReason !== null && slot.openPages === 0) {
        closing.push(this.retire(slot))
        continue
      }
      if (
        slot.retireReason === null &&
        slot.openPages === 0 &&
        now - slot.lastUsedAt >= this.options.idleTimeoutMs &&
        this.slots.size > 1
      ) {
        closing.push(this.retire(slot, 'idle'))
      }
    }
    await Promise.all(closing)
    this.notify()
  }

  /** Starts the watchdog. Returns the stop function; calling it twice is safe. */
  startWatchdog(intervalMs: number): () => void {
    const timer = setInterval(() => {
      void this.sweep()
    }, intervalMs)
    timer.unref()
    return () => clearInterval(timer)
  }

  stats(): PoolStats {
    let pages = 0
    for (const slot of this.slots) {
      pages += slot.openPages
    }
    return {
      browsers: this.slots.size,
      pages,
      waiting: this.waiters.size,
      launched: this.launched,
      recycled: this.recycled,
    }
  }

  /** Closes every browser. The pool refuses new leases afterwards; open pages close with their browser. */
  async close(): Promise<void> {
    this.closed = true
    const closing = [...this.slots].map((slot) => this.retire(slot, 'shutdown'))
    await Promise.all(closing)
    this.notify()
  }

  private pick(): Slot | undefined {
    for (const slot of this.slots) {
      if (slot.retireReason === null && slot.handle.isConnected()) {
        return slot
      }
    }
    return undefined
  }

  private async launchAndLease(
    accountId: string | null,
    deadline: number
  ): Promise<PageLease> {
    this.launching += 1
    try {
      const slot = await this.launch(accountId)
      return await this.lease(slot, accountId)
    } catch (error) {
      if (!(error instanceof WorkerError) && Date.now() >= deadline) {
        throw new WorkerError('timeout', 503, {
          detail: 'browser launch exceeded the acquire timeout',
          retryable: true,
          retryAfterSeconds: 1,
        })
      }
      throw error
    } finally {
      this.launching -= 1
    }
  }

  private async launch(accountId: string | null): Promise<Slot> {
    const proxyUrl = this.options.proxyFor?.(accountId) ?? null
    const handle = await this.options.driver.launch({ proxyUrl })
    const slot: Slot = {
      handle,
      openPages: 0,
      pagesServed: 0,
      lastUsedAt: this.options.clock.now().getTime(),
      retireReason: null,
    }
    this.slots.add(slot)
    this.launched += 1
    this.event({ type: 'launched', browserId: handle.id })
    return slot
  }

  private async lease(slot: Slot, accountId: string | null): Promise<PageLease> {
    // Count the page before the async call: two acquires in the same tick must not share the last slot's budget.
    slot.openPages += 1
    slot.pagesServed += 1
    slot.lastUsedAt = this.options.clock.now().getTime()
    let page: BrowserPage
    try {
      page = await slot.handle.newPage()
    } catch (error) {
      slot.openPages -= 1
      throw error
    }
    let released = false
    return {
      page,
      browserId: slot.handle.id,
      accountId,
      release: async (): Promise<void> => {
        if (released) {
          return
        }
        released = true
        try {
          await page.close()
        } catch {
          // The page is gone (crash, disconnect); the pool still reclaims its slot.
        }
        slot.openPages -= 1
        slot.lastUsedAt = this.options.clock.now().getTime()
        if (slot.retireReason !== null && slot.openPages === 0) {
          await this.retire(slot)
        }
        this.notify()
      },
    }
  }

  private markRetiring(slot: Slot, reason: PoolEvent['reason']): void {
    if (slot.retireReason !== null) {
      return
    }
    slot.retireReason = reason ?? null
    this.recycled += 1
    this.event({ type: 'recycled', browserId: slot.handle.id, reason })
  }

  private async retire(slot: Slot, reason?: PoolEvent['reason']): Promise<void> {
    if (!this.slots.delete(slot)) {
      return
    }
    this.event({ type: 'closed', browserId: slot.handle.id, reason: reason ?? slot.retireReason ?? undefined })
    try {
      await slot.handle.close()
    } catch {
      // A browser that refuses to close is already gone as far as the pool is concerned; the OS reaps it.
    }
  }

  private waitForSlot(remainingMs: number): Promise<void> {
    return new Promise<void>((resolve) => {
      const done = (): void => {
        clearTimeout(timer)
        this.waiters.delete(done)
        resolve()
      }
      const timer = setTimeout(done, remainingMs)
      timer.unref()
      this.waiters.add(done)
    })
  }

  private notify(): void {
    for (const waiter of [...this.waiters]) {
      waiter()
    }
  }

  private event(event: PoolEvent): void {
    this.options.onEvent?.(event)
  }
}
