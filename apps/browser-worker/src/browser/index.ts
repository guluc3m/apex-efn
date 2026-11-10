/**
 * Factory that turns the worker configuration into a ready pool (D5-02).
 *
 * Kept separate from ``pool.ts`` so the pool stays dependency-free and testable with a fake driver, and from
 * ``index.ts`` so a browser-based adapter can be added without touching the process bootstrap.
 */

import { systemClock } from '../clock.js'
import type { WorkerConfig } from '../config.js'

import { BrowserPool, type PoolEvent } from './pool.js'
import { StaticProxyResolver, type ProxyResolver } from './proxies.js'
import { createPuppeteerDriver } from './puppeteer-driver.js'

export type PoolConfig = Pick<
  WorkerConfig,
  | 'browserPoolSize'
  | 'maxPagesPerBrowser'
  | 'browserMaxMemoryMb'
  | 'browserAcquireTimeoutMs'
  | 'browserIdleTimeoutMs'
  | 'proxyResidentialUrl'
  | 'proxyDatacenterUrl'
>

export function createBrowserPool(
  config: PoolConfig,
  onEvent?: (event: PoolEvent) => void,
  proxy: ProxyResolver = new StaticProxyResolver({
    residentialUrl: config.proxyResidentialUrl,
    datacenterUrl: config.proxyDatacenterUrl,
  })
): BrowserPool {
  return new BrowserPool({
    maxBrowsers: config.browserPoolSize,
    maxPagesPerBrowser: config.maxPagesPerBrowser,
    maxMemoryMbPerBrowser: config.browserMaxMemoryMb,
    acquireTimeoutMs: config.browserAcquireTimeoutMs,
    idleTimeoutMs: config.browserIdleTimeoutMs,
    clock: systemClock,
    driver: createPuppeteerDriver(),
    proxyFor: (accountId) => proxy.resolve(accountId),
    ...(onEvent === undefined ? {} : { onEvent }),
  })
}
