import { format, inspect } from 'node:util'

import { afterEach, describe, expect, it, vi } from 'vitest'

import {
  InvalidIdentifierError,
  RedactedSecret,
  VaultClient,
  VaultError,
  VaultNotFoundError,
  parseCredentialRef,
} from './vault.js'

const TOKEN = 's.ts-unit-token-do-not-leak'
const SECRET = 'ts-secret-cookie-value-987'
const REF = 'cred_AAAAAAAAAAAAAAAAAAAAAA'
const ADDR = 'http://vault.test:8200'

type FetchCall = { url: string; init: RequestInit }

function jsonResponse(status: number, body: unknown): Response {
  return new Response(body === undefined ? null : JSON.stringify(body), {
    status,
    headers: { 'content-type': 'application/json' },
  })
}

function stubFetch(respond: (call: FetchCall) => Response | Promise<Response>): {
  calls: FetchCall[]
} {
  const calls: FetchCall[] = []
  const fn = vi.fn(async (url: string, init: RequestInit = {}) => {
    const call = { url, init }
    calls.push(call)
    return respond(call)
  })
  vi.stubGlobal('fetch', fn)
  return { calls }
}

function client(): VaultClient {
  return new VaultClient({ addr: ADDR, token: TOKEN })
}

afterEach(() => {
  vi.unstubAllGlobals()
  vi.restoreAllMocks()
})

describe('parseCredentialRef', () => {
  it('accepts the generated format', () => {
    expect(parseCredentialRef(REF)).toBe(REF)
  })

  it.each(['../../etc/passwd', 'cred_a/b', 'cred_short', `${REF}\n`, '', 'cred_..x'])(
    'rejects %j',
    (value) => {
      expect(() => parseCredentialRef(value)).toThrow(InvalidIdentifierError)
    }
  )
})

describe('VaultClient.getCredential', () => {
  it('reads the KV v2 data path with the token header and returns the payload', async () => {
    const { calls } = stubFetch(() =>
      jsonResponse(200, { data: { data: { username: 'buyer', password: SECRET }, metadata: {} } })
    )

    const payload = await client().getCredential('tenant-a', REF)

    expect(calls).toHaveLength(1)
    expect(calls[0]?.url).toBe(`${ADDR}/v1/apex-kv/data/tenants/tenant-a/credentials/${REF}`)
    expect(calls[0]?.init.method).toBe('GET')
    expect((calls[0]?.init.headers as Record<string, string>)['X-Vault-Token']).toBe(TOKEN)
    expect(payload.reveal()).toEqual({ username: 'buyer', password: SECRET })
  })

  it('rejects traversal in tenant_id and ref before sending any request', async () => {
    const { calls } = stubFetch(() => jsonResponse(200, {}))

    await expect(client().getCredential('../tenant-b', REF)).rejects.toBeInstanceOf(
      InvalidIdentifierError
    )
    await expect(client().getCredential('tenant-a', 'cred_../x')).rejects.toBeInstanceOf(
      InvalidIdentifierError
    )
    expect(calls).toHaveLength(0)
  })

  it('maps 404 to VaultNotFoundError', async () => {
    stubFetch(() => jsonResponse(404, { errors: [] }))

    const error = await client()
      .getCredential('tenant-a', REF)
      .catch((e: unknown) => e)
    expect(error).toBeInstanceOf(VaultNotFoundError)
    expect((error as VaultError).status).toBe(404)
  })

  it('keeps secrets and the token out of error messages', async () => {
    stubFetch(() => jsonResponse(500, { errors: [`boom ${SECRET} ${TOKEN}`] }))

    const error = await client()
      .getCredential('tenant-a', REF)
      .catch((e: unknown) => e)
    expect(error).toBeInstanceOf(VaultError)
    expect((error as VaultError).message).not.toContain(SECRET)
    expect((error as VaultError).message).not.toContain(TOKEN)
    expect((error as VaultError).operation).toBe('get_credential')
  })

  it('wraps transport errors without exposing the underlying message', async () => {
    stubFetch(() => {
      throw new TypeError(`connect refused ${TOKEN}`)
    })

    const error = await client()
      .getCredential('tenant-a', REF)
      .catch((e: unknown) => e)
    expect(error).toBeInstanceOf(VaultError)
    expect((error as VaultError).message).toContain('transport error')
    expect((error as VaultError).message).not.toContain(TOKEN)
  })

  it('rejects responses with an unexpected shape', async () => {
    stubFetch(() => jsonResponse(200, { data: { unexpected: true } }))

    await expect(client().getCredential('tenant-a', REF)).rejects.toThrow(
      'unexpected response shape'
    )
  })
})

describe('VaultClient session state', () => {
  it('writes session state as a KV v2 data body', async () => {
    const { calls } = stubFetch(() => jsonResponse(200, { data: { version: 1 } }))
    const state = { cookies: [{ name: 'sid', value: SECRET }] }

    await client().putSessionState('tenant-a', 'acct-1', state)

    expect(calls[0]?.url).toBe(`${ADDR}/v1/apex-kv/data/tenants/tenant-a/browser-sessions/acct-1`)
    expect(calls[0]?.init.method).toBe('POST')
    expect(JSON.parse(calls[0]?.init.body as string)).toEqual({ data: state })
  })

  it('reads session state back', async () => {
    stubFetch(() =>
      jsonResponse(200, { data: { data: { cookies: [{ name: 'sid', value: SECRET }] } } })
    )

    const payload = await client().getSessionState('tenant-a', 'acct-1')
    expect(payload.reveal()).toEqual({ cookies: [{ name: 'sid', value: SECRET }] })
  })

  it('rejects account ids with path characters', async () => {
    const { calls } = stubFetch(() => jsonResponse(200, {}))

    await expect(client().getSessionState('tenant-a', '../x')).rejects.toBeInstanceOf(
      InvalidIdentifierError
    )
    await expect(client().putSessionState('tenant-a', 'a/b', {})).rejects.toBeInstanceOf(
      InvalidIdentifierError
    )
    expect(calls).toHaveLength(0)
  })
})

describe('redaction', () => {
  async function secretPayload(): Promise<RedactedSecret<Record<string, unknown>>> {
    stubFetch(() => jsonResponse(200, { data: { data: { password: SECRET } } }))
    return client().getCredential('tenant-a', REF)
  }

  it('hides the value from JSON serialisation', async () => {
    const payload = await secretPayload()
    expect(JSON.stringify(payload)).toBe('"[REDACTED]"')
    expect(JSON.stringify({ nested: payload })).not.toContain(SECRET)
  })

  it('hides the value from String(), template strings and format()', async () => {
    const payload = await secretPayload()
    expect(String(payload)).toBe('[REDACTED]')
    expect(`${payload.toString()}`).not.toContain(SECRET)
    expect(format('%s %o', payload, payload)).not.toContain(SECRET)
  })

  it('hides the value from util.inspect and console-style output', async () => {
    const payload = await secretPayload()
    expect(inspect(payload)).toContain('[REDACTED]')
    expect(inspect(payload)).not.toContain(SECRET)
    expect(inspect({ payload })).not.toContain(SECRET)
    expect(Object.keys(payload)).toEqual([])
  })

  it('keeps the token out of client string forms', () => {
    const vault = client()
    expect(String(vault)).not.toContain(TOKEN)
    expect(inspect(vault)).not.toContain(TOKEN)
    expect(JSON.stringify({ vault })).not.toContain(TOKEN)
  })
})

describe('VaultClient.fromEnv', () => {
  it('requires VAULT_ADDR and VAULT_TOKEN', () => {
    expect(() => VaultClient.fromEnv({ VAULT_ADDR: ADDR })).toThrow(VaultError)
    expect(() => VaultClient.fromEnv({ VAULT_TOKEN: TOKEN })).toThrow(VaultError)
  })

  it('builds a client from the environment', async () => {
    const { calls } = stubFetch(() => jsonResponse(404, { errors: [] }))

    await VaultClient.fromEnv({ VAULT_ADDR: `${ADDR}/`, VAULT_TOKEN: TOKEN })
      .getCredential('tenant-a', REF)
      .catch(() => undefined)

    expect(calls[0]?.url).toBe(`${ADDR}/v1/apex-kv/data/tenants/tenant-a/credentials/${REF}`)
  })
})

const integrationAddr = process.env.VAULT_INTEGRATION_ADDR

describe.skipIf(!integrationAddr)('VaultClient against a real Vault', () => {
  const token = process.env.VAULT_INTEGRATION_TOKEN ?? process.env.VAULT_TOKEN ?? ''

  it('round-trips session state through the dev server', async () => {
    const vault = new VaultClient({ addr: integrationAddr ?? '', token })
    const account = `acct-ts-${Date.now().toString(36)}`
    const state = { cookies: [{ name: 'sid', value: 'it-ts-cookie' }] }

    await vault.putSessionState('tenant-a', account, state)
    const payload = await vault.getSessionState('tenant-a', account)
    expect(payload.reveal()).toEqual(state)
    expect(JSON.stringify(payload)).not.toContain('it-ts-cookie')
  })
})
