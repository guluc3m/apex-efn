import { describe, expect, it } from 'vitest'

import { WorkerError } from '../errors.js'
import { VaultClient } from '../platform/vault.js'

import {
  SessionManager,
  sessionErrorFor,
  VaultSessionStore,
  type SessionStore,
  type SessionSurface,
  type StoredSession,
  type StorageItem,
  type StoredCookie,
} from './sessions.js'

function clock(): { now: () => Date } {
  return { now: () => new Date('2026-11-10T12:00:00.000Z') }
}

class FakeStore implements SessionStore {
  readonly documents = new Map<string, StoredSession>()

  load(tenantId: string, accountId: string): Promise<StoredSession | null> {
    return Promise.resolve(this.documents.get(`${tenantId}/${accountId}`) ?? null)
  }

  save(tenantId: string, accountId: string, session: StoredSession): Promise<void> {
    this.documents.set(`${tenantId}/${accountId}`, session)
    return Promise.resolve()
  }
}

class FakeSurface implements SessionSurface {
  cookiesValue: StoredCookie[] = []
  readonly applied: StoredCookie[] = []
  readonly storageByOrigin = new Map<string, StorageItem[]>()

  cookies(): Promise<StoredCookie[]> {
    return Promise.resolve(this.cookiesValue)
  }

  setCookies(cookies: StoredCookie[]): Promise<void> {
    this.applied.push(...cookies)
    return Promise.resolve()
  }

  storage(origin: string): Promise<StorageItem[]> {
    return Promise.resolve(this.storageByOrigin.get(origin) ?? [])
  }

  setStorage(origin: string, items: StorageItem[]): Promise<void> {
    this.storageByOrigin.set(origin, items)
    return Promise.resolve()
  }
}

const COOKIE: StoredCookie = {
  name: 'session',
  value: 'abc123',
  domain: 'market.example',
  path: '/',
  secure: true,
}

function session(overrides: Partial<StoredSession> = {}): StoredSession {
  return {
    version: 1,
    cookies: [COOKIE],
    origins: [{ origin: 'https://market.example', items: [{ name: 'lang', value: 'es' }] }],
    updatedAt: '2026-11-09T10:00:00.000Z',
    needsReauth: false,
    reason: null,
    ...overrides,
  }
}

describe('SessionManager', () => {
  it('restores cookies and origin storage of the account', async () => {
    const store = new FakeStore()
    await store.save('t1', 'acct', session())
    const surface = new FakeSurface()

    const result = await new SessionManager(store, clock()).restore(surface, 't1', 'acct')

    expect(result).toBe('restored')
    expect(surface.applied).toEqual([COOKIE])
    expect(surface.storageByOrigin.get('https://market.example')).toEqual([{ name: 'lang', value: 'es' }])
  })

  it('reports an account with no stored session instead of pretending', async () => {
    const result = await new SessionManager(new FakeStore(), clock()).restore(
      new FakeSurface(),
      't1',
      'acct'
    )
    expect(result).toBe('missing')
  })

  it('refuses to use a session a platform rejected', async () => {
    const store = new FakeStore()
    await store.save('t1', 'acct', session({ needsReauth: true, reason: 'session_invalid' }))
    const surface = new FakeSurface()

    const result = await new SessionManager(store, clock()).restore(surface, 't1', 'acct')

    expect(result).toBe('needs_reauth')
    expect(surface.applied).toEqual([]) // stale cookies are never replayed
  })

  it('persists what the page has and bumps the version', async () => {
    const store = new FakeStore()
    await store.save('t1', 'acct', session())
    const surface = new FakeSurface()
    surface.cookiesValue = [COOKIE, { ...COOKIE, name: 'csrf' }]

    const saved = await new SessionManager(store, clock()).persist(surface, 't1', 'acct')

    expect(saved.version).toBe(2)
    expect(saved.cookies).toHaveLength(2)
    expect(saved.updatedAt).toBe('2026-11-10T12:00:00.000Z')
    expect(saved.needsReauth).toBe(false)
    await expect(store.load('t1', 'acct')).resolves.toEqual(saved)
  })

  it('persists a brand new account starting at version 1', async () => {
    const surface = new FakeSurface()
    surface.cookiesValue = [COOKIE]

    const saved = await new SessionManager(new FakeStore(), clock()).persist(
      surface,
      't1',
      'acct'
    )

    expect(saved.version).toBe(1)
    expect(saved.origins).toEqual([])
  })

  it('marks a rejected session and keeps the previous data for forensics', async () => {
    const store = new FakeStore()
    await store.save('t1', 'acct', session())
    const manager = new SessionManager(store, clock())

    const marked = await manager.invalidate('t1', 'acct', 'captcha')

    expect(marked.needsReauth).toBe(true)
    expect(marked.reason).toBe('captcha')
    expect(marked.cookies).toEqual([COOKIE])
    expect(marked.version).toBe(1) // marking is not a refresh
  })

  it('restores again after a human writes a fresh session into the store', async () => {
    const store = new FakeStore()
    await store.save('t1', 'acct', session({ needsReauth: true, reason: 'captcha' }))
    const manager = new SessionManager(store, clock())
    expect(await manager.restore(new FakeSurface(), 't1', 'acct')).toBe('needs_reauth')

    // What a human does out of band: write a new document for the same account.
    await store.save('t1', 'acct', session({ version: 2, needsReauth: false }))

    expect(await manager.restore(new FakeSurface(), 't1', 'acct')).toBe('restored')
  })
})

describe('sessionErrorFor', () => {
  it('turns a missing or rejected session into session_invalid', () => {
    const missing = sessionErrorFor('missing')
    const rejected = sessionErrorFor('needs_reauth')

    expect(missing).toBeInstanceOf(WorkerError)
    expect(missing?.code).toBe('session_invalid')
    expect(rejected?.code).toBe('session_invalid')
    expect(rejected?.detail).toMatch(/human/i)
  })

  it('returns nothing for a restored session', () => {
    expect(sessionErrorFor('restored')).toBeNull()
  })
})

describe('VaultSessionStore', () => {
  function kv(payload: unknown): Response {
    return new Response(JSON.stringify({ data: { data: payload } }), {
      status: 200,
      headers: { 'content-type': 'application/json' },
    })
  }

  function vaultWith(response: () => Response): { client: VaultClient; calls: string[] } {
    const calls: string[] = []
    const fetchImpl = ((url: string | URL | Request, init?: RequestInit) => {
      const href = typeof url === 'string' ? url : url instanceof URL ? url.href : url.url
      calls.push(`${init?.method ?? 'GET'} ${href}`)
      return Promise.resolve(response())
    }) as typeof fetch
    return {
      client: new VaultClient({ addr: 'http://vault.test:8200', token: 't'.repeat(32), fetchImpl }),
      calls,
    }
  }

  it('reads the session from the account path', async () => {
    const { client, calls } = vaultWith(() => kv(session()))
    const loaded = await new VaultSessionStore(client).load('tenant-a', 'acct-1')

    expect(loaded).toEqual(session())
    expect(calls[0]).toContain('/v1/apex-kv/data/tenants/tenant-a/browser-sessions/acct-1')
  })

  it('treats a missing document as a new account', async () => {
    const { client } = vaultWith(() => new Response(null, { status: 404 }))
    await expect(new VaultSessionStore(client).load('tenant-a', 'acct-1')).resolves.toBeNull()
  })

  it('refuses a document it cannot understand instead of starting empty', async () => {
    const { client } = vaultWith(() => kv({ version: 1, cookies: 'not-an-array' }))
    await expect(new VaultSessionStore(client).load('tenant-a', 'acct-1')).rejects.toMatchObject({
      code: 'session_invalid',
    })
  })

  it('writes the whole document back to the same path', async () => {
    const { client, calls } = vaultWith(() => new Response('{}', { status: 200 }))
    await new VaultSessionStore(client).save('tenant-a', 'acct-1', session({ version: 3 }))

    expect(calls[0]).toBe(
      'POST http://vault.test:8200/v1/apex-kv/data/tenants/tenant-a/browser-sessions/acct-1'
    )
  })
})
