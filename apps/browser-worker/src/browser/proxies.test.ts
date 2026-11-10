import { describe, expect, it } from 'vitest'

import { StaticProxyResolver } from './proxies.js'

const RESIDENTIAL = 'http://residential.example:8000'
const DATACENTER = 'http://datacenter.example:8000'

describe('StaticProxyResolver', () => {
  it('prefers the configured family', async () => {
    const resolver = new StaticProxyResolver({
      residentialUrl: RESIDENTIAL,
      datacenterUrl: DATACENTER,
      family: 'datacenter',
    })

    await expect(resolver.resolve('acct-1')).resolves.toBe(DATACENTER)
  })

  it('falls back to the other family when the preferred one is unset', async () => {
    const resolver = new StaticProxyResolver({ datacenterUrl: DATACENTER })
    await expect(resolver.resolve(null)).resolves.toBe(DATACENTER)
  })

  it('gives an account its own proxy when it has one', async () => {
    const resolver = new StaticProxyResolver({
      residentialUrl: RESIDENTIAL,
      perAccount: { paid: { url: 'http://paid.example:8000', family: 'residential' } },
    })

    await expect(resolver.resolve('paid')).resolves.toBe('http://paid.example:8000')
    await expect(resolver.resolve('free')).resolves.toBe(RESIDENTIAL)
  })

  it('answers null when nothing is configured, which means "no proxy"', async () => {
    await expect(new StaticProxyResolver({}).resolve('acct-1')).resolves.toBeNull()
  })
})
