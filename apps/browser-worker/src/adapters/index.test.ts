import { describe, expect, it } from 'vitest'

import { WorkerError } from '../errors.js'
import { StaticFlags } from '../platform/flags.js'
import { FakePlatformAdapter } from '../testing/fakes.js'

import { AdapterRegistry } from './index.js'

function errorOf(action: () => unknown): unknown {
  try {
    action()
  } catch (error) {
    return error
  }
  return undefined
}

describe('AdapterRegistry', () => {
  const flags = new StaticFlags({
    'platform.mock-a.enabled': true,
    'platform.mock-c.enabled': false,
  })

  it('returns an enabled adapter', () => {
    const adapter = new FakePlatformAdapter('mock-a', 'http')
    expect(new AdapterRegistry([adapter], flags).require('mock-a')).toBe(adapter)
  })

  it('reports an unknown platform as 404', () => {
    const registry = new AdapterRegistry([], flags)
    expect(errorOf(() => registry.require('nope'))).toBeInstanceOf(WorkerError)
    expect(errorOf(() => registry.require('nope'))).toMatchObject({
      code: 'unknown_platform',
      status: 404,
    })
  })

  it('refuses a disabled platform as 409', () => {
    const registry = new AdapterRegistry([new FakePlatformAdapter('mock-c', 'http')], flags)
    expect(errorOf(() => registry.require('mock-c'))).toMatchObject({
      code: 'platform_disabled',
      status: 409,
    })
  })

  it('reports the enabled flag for each platform', () => {
    const registry = new AdapterRegistry(
      [new FakePlatformAdapter('mock-a', 'http'), new FakePlatformAdapter('mock-c', 'http')],
      flags
    )
    expect(registry.status()).toEqual([
      { platform: 'mock-a', enabled: true, transport: 'http' },
      { platform: 'mock-c', enabled: false, transport: 'http' },
    ])
  })

  it('rejects a platform id that cannot have a flag', () => {
    expect(() => new AdapterRegistry([new FakePlatformAdapter('Bad Id', 'http')], flags)).toThrow()
  })
})
