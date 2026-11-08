import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'

import {
  type FlagProvider,
  StaticFlags,
  UnleashFlags,
  platformFlagName,
  validateFlagName,
} from './flags'

const TOKEN = 'default:development.apex-dev-unleash-client-SECRET-XYZ'
const BASE_URL = 'http://unleash.test:4242/api/'
const NOW = new Date('2026-11-08T10:00:00Z')

// Shaped like GET /api/client/features on unleash-server 8.x (client API, "version": 2).
const FEATURES_PAYLOAD = {
  version: 2,
  features: [
    {
      name: 'platform.mock-a.enabled',
      type: 'release',
      project: 'default',
      enabled: true,
      stale: false,
      strategies: [{ name: 'default', constraints: [], parameters: {}, segments: [] }],
      variants: [],
      impressionData: false,
    },
    {
      name: 'platform.mock-b.enabled',
      type: 'release',
      project: 'default',
      enabled: false,
      stale: false,
      strategies: [{ name: 'default', constraints: [], parameters: {}, segments: [] }],
      variants: [],
      impressionData: false,
    },
    {
      name: 'negotiation.autonomous_send',
      type: 'kill-switch',
      project: 'default',
      enabled: true,
      stale: false,
      strategies: [
        {
          name: 'flexibleRollout',
          constraints: [],
          parameters: { rollout: '0', stickiness: 'default', groupId: 'x' },
          segments: [],
        },
      ],
      variants: [],
      impressionData: false,
    },
    {
      name: 'sanity.bands.v1',
      type: 'release',
      project: 'default',
      enabled: true,
      stale: false,
      strategies: [
        {
          name: 'flexibleRollout',
          constraints: [],
          parameters: { rollout: '50', stickiness: 'default', groupId: 'y' },
          segments: [],
        },
      ],
      variants: [],
      impressionData: false,
    },
    {
      name: 'trust.model.v2',
      type: 'release',
      project: 'default',
      enabled: true,
      stale: false,
      strategies: [
        {
          name: 'default',
          constraints: [
            {
              contextName: 'appName',
              operator: 'IN',
              values: ['apex-browser-worker'],
              caseInsensitive: false,
              inverted: false,
            },
          ],
          parameters: {},
          segments: [],
        },
      ],
      variants: [],
      impressionData: false,
    },
    {
      name: 'negotiation.strategy.anchor-first',
      type: 'release',
      project: 'default',
      enabled: true,
      stale: false,
      strategies: [
        { name: 'userWithId', constraints: [], parameters: { userIds: 'u1' }, segments: [] },
      ],
      variants: [],
      impressionData: false,
    },
    {
      name: 'negotiation.strategy.volume-tiers',
      type: 'release',
      project: 'default',
      enabled: true,
      stale: false,
      strategies: [],
      variants: [],
      impressionData: false,
    },
  ],
  query: { environment: 'development', namePrefix: '', tag: [] },
}

function jsonResponse(body: unknown, status = 200): Response {
  return new Response(JSON.stringify(body), {
    status,
    headers: { 'content-type': 'application/json' },
  })
}

function mockFeatures(payload: unknown = FEATURES_PAYLOAD) {
  const fetchMock = vi.fn(() => Promise.resolve(jsonResponse(payload)))
  vi.stubGlobal('fetch', fetchMock)
  return fetchMock
}

function clientWith(overrides: Partial<ConstructorParameters<typeof UnleashFlags>[0]> = {}) {
  return new UnleashFlags({
    baseUrl: BASE_URL,
    clientToken: TOKEN,
    now: () => NOW,
    ...overrides,
  })
}

async function serving(payload: unknown = FEATURES_PAYLOAD): Promise<UnleashFlags> {
  mockFeatures(payload)
  const client = clientWith()
  expect(await client.refresh()).toBe(true)
  return client
}

let warnSpy: ReturnType<typeof vi.spyOn>

beforeEach(() => {
  warnSpy = vi.spyOn(console, 'warn').mockImplementation(() => undefined)
})

afterEach(() => {
  vi.unstubAllGlobals()
  vi.useRealTimers()
  vi.restoreAllMocks()
})

describe('naming convention', () => {
  it.each([
    'platform.mock-a.enabled',
    'negotiation.strategy.anchor_first',
    'negotiation.autonomous_send',
    'sanity.bands.v1',
    'trust.model.v2',
  ])('accepts %s', (name) => {
    expect(validateFlagName(name)).toBe(name)
  })

  it.each([
    'Platform.mock-a.enabled',
    'platform.mock-a',
    'platform.mock a.enabled',
    'platform..enabled',
    'platform.mock-a.enabled.extra',
    'sanity.bands.v1.0',
    'negotiation.autonomous-send',
    'something.else',
    '',
  ])('rejects %j', (name) => {
    expect(() => validateFlagName(name)).toThrow(/malformed feature flag name/)
  })

  it('builds platform flag names', () => {
    expect(platformFlagName('mock-a')).toBe('platform.mock-a.enabled')
  })
})

describe('UnleashFlags', () => {
  it('unknown flag is off', async () => {
    const client = await serving()
    expect(client.isEnabled('platform.unknown-one.enabled')).toBe(false)
  })

  it('a flag never fetched is off', () => {
    mockFeatures()
    expect(clientWith().isPlatformEnabled('mock-a')).toBe(false)
  })

  it('unreachable server is off, does not throw, and logs the error name only', async () => {
    vi.stubGlobal(
      'fetch',
      vi.fn(() => Promise.reject(new TypeError('fetch failed')))
    )
    const client = clientWith()
    await expect(client.refresh()).resolves.toBe(false)
    expect(client.isEnabled('platform.mock-a.enabled')).toBe(false)
    expect(warnSpy.mock.calls.flat().join('\n')).toContain('TypeError')
  })

  it('HTTP 401 keeps the last snapshot and reports the status', async () => {
    const client = await serving()
    vi.stubGlobal(
      'fetch',
      vi.fn(() => Promise.resolve(jsonResponse({ error: 'bad' }, 401)))
    )
    expect(await client.refresh()).toBe(false)
    expect(client.isPlatformEnabled('mock-a')).toBe(true)
    expect(warnSpy.mock.calls.flat().join('\n')).toContain('HTTP 401')
  })

  it('malformed payload keeps the last snapshot', async () => {
    const client = await serving()
    vi.stubGlobal(
      'fetch',
      vi.fn(() => Promise.resolve(jsonResponse({ nope: true })))
    )
    expect(await client.refresh()).toBe(false)
    expect(client.isPlatformEnabled('mock-a')).toBe(true)
  })

  it('disabled toggle is off', async () => {
    const client = await serving()
    expect(client.isPlatformEnabled('mock-b')).toBe(false)
  })

  it('enabled with default strategy is on', async () => {
    const client = await serving()
    expect(client.isPlatformEnabled('mock-a')).toBe(true)
  })

  it('flexibleRollout 100 is on, 0 is off', async () => {
    const payload = structuredClone(FEATURES_PAYLOAD)
    const rollout = payload.features[2]!.strategies[0]! as { parameters: { rollout: string } }
    rollout.parameters.rollout = '100'
    const client = await serving(payload)
    expect(client.isEnabled('negotiation.autonomous_send')).toBe(true)

    rollout.parameters.rollout = '0'
    const offClient = await serving(payload)
    expect(offClient.isEnabled('negotiation.autonomous_send')).toBe(false)
  })

  it('partial flexibleRollout is off and logged once', async () => {
    const client = await serving()
    expect(client.isEnabled('sanity.bands.v1')).toBe(false)
    expect(client.isEnabled('sanity.bands.v1')).toBe(false)
    const messages = warnSpy.mock.calls.flat().filter((m) => String(m).includes('partial rollout'))
    expect(messages).toHaveLength(1)
  })

  it('unknown strategy is off', async () => {
    const client = await serving()
    expect(client.isEnabled('negotiation.strategy.anchor-first')).toBe(false)
  })

  it('strategy with constraints is off', async () => {
    const client = await serving()
    expect(client.isEnabled('trust.model.v2')).toBe(false)
  })

  it('enabled toggle with no strategies is on', async () => {
    const client = await serving()
    expect(client.isEnabled('negotiation.strategy.volume-tiers')).toBe(true)
  })

  it('strategies are OR-ed: a constrained strategy does not block a default one', async () => {
    const payload = structuredClone(FEATURES_PAYLOAD)
    payload.features[0]!.strategies.push({
      name: 'flexibleRollout',
      constraints: [{ contextName: 'x', operator: 'IN', values: ['y'] }],
      parameters: { rollout: '100' },
      segments: [],
    } as never)
    const client = await serving(payload)
    expect(client.isPlatformEnabled('mock-a')).toBe(true)
  })

  it('disabled strategy is off', async () => {
    const payload = structuredClone(FEATURES_PAYLOAD)
    payload.features[0]!.strategies = [
      { name: 'default', constraints: [], disabled: true } as never,
    ]
    const client = await serving(payload)
    expect(client.isPlatformEnabled('mock-a')).toBe(false)
  })

  it('throws on malformed names instead of answering false', async () => {
    const client = await serving()
    expect(() => client.isEnabled('platform.mock-a')).toThrow(/malformed feature flag name/)
    expect(() => new StaticFlags().isEnabled('platform.mock-a')).toThrow(/malformed/)
  })

  it('polls until stopped (fake timers)', async () => {
    vi.useFakeTimers()
    const fetchMock = mockFeatures()
    const client = clientWith()
    const stop = client.startPolling(1000)
    await vi.advanceTimersByTimeAsync(2500)
    const callsWhileRunning = fetchMock.mock.calls.length
    expect(callsWhileRunning).toBeGreaterThanOrEqual(3)
    stop()
    await vi.advanceTimersByTimeAsync(5000)
    expect(fetchMock.mock.calls.length).toBe(callsWhileRunning)
  })

  it('sends the token and identity headers and normalises the trailing slash', async () => {
    const fetchMock = mockFeatures()
    const client = new UnleashFlags({
      baseUrl: 'http://unleash.test/api///',
      clientToken: TOKEN,
      appName: 'apex-browser-worker',
      instanceId: 'pod-1',
    })
    await client.refresh()
    const [url, init] = fetchMock.mock.calls[0] as unknown as [string, RequestInit]
    expect(url).toBe('http://unleash.test/api/client/features')
    const headers = init.headers as Record<string, string>
    expect(headers.Authorization).toBe(TOKEN)
    expect(headers['UNLEASH-APPNAME']).toBe('apex-browser-worker')
    expect(headers['UNLEASH-INSTANCEID']).toBe('pod-1')
  })

  it('records lastRefreshed from the injected clock', async () => {
    mockFeatures()
    const client = clientWith()
    expect(client.lastRefreshed).toBeNull()
    await client.refresh()
    expect(client.lastRefreshed).toEqual(NOW)
  })

  it('token never appears in logs', async () => {
    vi.stubGlobal(
      'fetch',
      vi.fn((_url: string, init: RequestInit) => {
        const auth = (init.headers as Record<string, string>).Authorization
        return Promise.resolve(new Response(`bad token echoed ${auth}`, { status: 401 }))
      })
    )
    const client = clientWith()
    await client.refresh()
    client.isPlatformEnabled('mock-a')
    client.isEnabled('negotiation.strategy.anchor-first')
    const logged = warnSpy.mock.calls.flat().map(String).join('\n')
    expect(logged).not.toContain(TOKEN)
    expect(logged).not.toContain('SECRET-XYZ')
  })

  it('fromEnv requires URL and token', () => {
    expect(() => UnleashFlags.fromEnv({ UNLEASH_URL: 'http://x/api' })).toThrow(/must be set/)
    expect(() => UnleashFlags.fromEnv({ UNLEASH_API_TOKEN: TOKEN })).toThrow(/must be set/)
  })

  it('fromEnv builds a working client', async () => {
    mockFeatures()
    const client = UnleashFlags.fromEnv({
      UNLEASH_URL: 'http://unleash.test:4242/api',
      UNLEASH_API_TOKEN: TOKEN,
    })
    expect(await client.refresh()).toBe(true)
    expect(client.isPlatformEnabled('mock-a')).toBe(true)
  })
})

describe('StaticFlags', () => {
  it('implements the provider contract', () => {
    const flags: FlagProvider = new StaticFlags({
      'platform.mock-a.enabled': true,
      'negotiation.autonomous_send': false,
    })
    expect(flags.isPlatformEnabled('mock-a')).toBe(true)
    expect(flags.isPlatformEnabled('mock-b')).toBe(false)
    expect(flags.isEnabled('negotiation.autonomous_send')).toBe(false)
    expect(flags.isEnabled('sanity.bands.v9')).toBe(false)
  })
})

describe('D1-08 done when: a disabled platform is never called', () => {
  // Minimal stand-in for the D5-03 adapter registry: it only consults the flag provider.
  interface Adapter {
    id: string
    search: (query: string) => Promise<string[]>
  }

  function makeRegistry(adapters: Adapter[], flags: FlagProvider) {
    return {
      async searchAll(query: string): Promise<string[]> {
        const results: string[] = []
        for (const adapter of adapters) {
          if (!flags.isPlatformEnabled(adapter.id)) continue
          results.push(...(await adapter.search(query)))
        }
        return results
      },
    }
  }

  function countingAdapter(id: string) {
    const search = vi.fn((query: string) => Promise.resolve([`${id}:${query}`]))
    return { adapter: { id, search } satisfies Adapter, search }
  }

  it('search is never called while platform.mock-a.enabled is off, and once when it is on', async () => {
    const mockA = countingAdapter('mock-a')
    const mockB = countingAdapter('mock-b')
    const killed = {
      ...FEATURES_PAYLOAD,
      features: FEATURES_PAYLOAD.features.map((f) =>
        f.name === 'platform.mock-a.enabled' ? { ...f, enabled: false } : f
      ),
    }

    // Same registry and same code path throughout; only the flag payload changes.
    const fetchMock = mockFeatures(killed)
    const flags = clientWith()
    const registryOnFlags = makeRegistry([mockA.adapter, mockB.adapter], flags)
    await flags.refresh()
    expect(await registryOnFlags.searchAll('laptop')).toEqual([])
    expect(mockA.search).not.toHaveBeenCalled()

    fetchMock.mockImplementation(() => Promise.resolve(jsonResponse(FEATURES_PAYLOAD)))
    await flags.refresh()
    expect(await registryOnFlags.searchAll('laptop')).toEqual(['mock-a:laptop'])
    expect(mockA.search).toHaveBeenCalledTimes(1)
    expect(mockB.search).not.toHaveBeenCalled()
  })
})
