import { describe, expect, it } from 'vitest'

import { loadConfig } from './config.js'

const TOKEN = 'a'.repeat(40)

describe('loadConfig', () => {
  it('applies the documented defaults', () => {
    const config = loadConfig({ BROWSER_WORKER_TOKEN: TOKEN })
    expect(config).toMatchObject({
      redisUrl: 'redis://localhost:6379',
      host: '0.0.0.0',
      port: 4010,
      token: TOKEN,
      scrapingConcurrency: 3,
      jobAttempts: 3,
      jobBackoffMs: 2000,
      idempotencyTtlSeconds: 86400,
      browserPoolSize: 5,
      maxPagesPerBrowser: 50,
      proxyResidentialUrl: undefined,
      proxyDatacenterUrl: undefined,
      artifactDir: './artifacts',
    })
  })

  it('coerces numeric values from strings', () => {
    const config = loadConfig({
      BROWSER_WORKER_TOKEN: TOKEN,
      PORT: '5000',
      SCRAPING_CONCURRENCY: '7',
    })
    expect(config.port).toBe(5000)
    expect(config.scrapingConcurrency).toBe(7)
  })

  it('treats an empty optional proxy URL as unset', () => {
    const config = loadConfig({ BROWSER_WORKER_TOKEN: TOKEN, PROXY_DATACENTER_URL: '' })
    expect(config.proxyDatacenterUrl).toBeUndefined()
  })

  it('rejects a missing token and names only the key', () => {
    expect(() => loadConfig({})).toThrow('BROWSER_WORKER_TOKEN')
  })

  it('rejects a short token without echoing its value', () => {
    const short = 'short-secret-value'
    let message = ''
    try {
      loadConfig({ BROWSER_WORKER_TOKEN: short })
    } catch (error) {
      message = error instanceof Error ? error.message : ''
    }
    expect(message).toContain('BROWSER_WORKER_TOKEN')
    expect(message).not.toContain(short)
  })

  it('rejects an invalid number and names only the key', () => {
    let message = ''
    try {
      loadConfig({ BROWSER_WORKER_TOKEN: TOKEN, JOB_ATTEMPTS: 'not-a-number' })
    } catch (error) {
      message = error instanceof Error ? error.message : ''
    }
    expect(message).toContain('JOB_ATTEMPTS')
    expect(message).not.toContain('not-a-number')
  })

  it('rejects a non-positive concurrency', () => {
    expect(() => loadConfig({ BROWSER_WORKER_TOKEN: TOKEN, SCRAPING_CONCURRENCY: '0' })).toThrow(
      'SCRAPING_CONCURRENCY'
    )
  })
})
