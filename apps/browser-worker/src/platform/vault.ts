/**
 * Vault KV v2 client for the browser worker (DEV-1 owns this file, see docs/security/secrets.md).
 *
 * The worker reads marketplace credentials and reads/writes encrypted browser session state. It never
 * returns credential values to the orchestrator or to the LLM. Accounts are referenced by opaque IDs.
 * Secret values are wrapped in RedactedSecret, so they do not show up in JSON, logs or string conversion.
 */

import { z } from 'zod'

const KV_MOUNT = 'trato-kv'

const TENANT_RE = /^[a-z0-9][a-z0-9-]{0,62}$/
const ACCOUNT_RE = /^[A-Za-z0-9][A-Za-z0-9_-]{0,127}$/
const REF_RE = /^cred_[A-Za-z0-9_-]{16,64}$/

export type CredentialRef = string & { readonly __brand: 'CredentialRef' }

export class InvalidIdentifierError extends Error {
  constructor(kind: string) {
    super(`invalid ${kind}`)
    this.name = 'InvalidIdentifierError'
  }
}

export class VaultError extends Error {
  readonly operation: string
  readonly status: number | undefined

  constructor(operation: string, status: number | undefined, detail?: string) {
    const statusPart = status === undefined ? '' : ` (HTTP ${status})`
    const detailPart = detail ? `: ${detail}` : ''
    super(`Vault ${operation} failed${statusPart}${detailPart}`)
    this.name = 'VaultError'
    this.operation = operation
    this.status = status
  }
}

export class VaultNotFoundError extends VaultError {
  constructor(operation: string) {
    super(operation, 404)
    this.name = 'VaultNotFoundError'
  }
}

const REDACTED = '[REDACTED]'

/** Holds a secret value. Only reveal() returns it. Every string or JSON conversion is redacted. */
export class RedactedSecret<T> {
  readonly #value: T

  constructor(value: T) {
    this.#value = value
  }

  reveal(): T {
    return this.#value
  }

  toJSON(): string {
    return REDACTED
  }

  toString(): string {
    return REDACTED
  }

  [Symbol.for('nodejs.util.inspect.custom')](): string {
    return REDACTED
  }
}

export type CredentialPayload = RedactedSecret<Record<string, unknown>>

export interface VaultClientOptions {
  addr: string
  token: string
  /** Defaults to the global fetch, resolved on each call so test stubs apply. */
  fetchImpl?: typeof fetch
  timeoutMs?: number
}

const kvReadBody = z.object({
  data: z.object({
    data: z.record(z.string(), z.unknown()),
  }),
})

export function parseCredentialRef(value: string): CredentialRef {
  if (!REF_RE.test(value)) {
    throw new InvalidIdentifierError('credential reference')
  }
  return value as CredentialRef
}

function tenantSegment(tenantId: string): string {
  if (!TENANT_RE.test(tenantId)) {
    throw new InvalidIdentifierError('tenant_id')
  }
  return tenantId
}

function accountSegment(accountId: string): string {
  if (!ACCOUNT_RE.test(accountId)) {
    throw new InvalidIdentifierError('account_id')
  }
  return accountId
}

export class VaultClient {
  readonly #addr: string
  readonly #token: RedactedSecret<string>
  readonly #fetchImpl: typeof fetch | undefined
  readonly #timeoutMs: number

  constructor(options: VaultClientOptions) {
    this.#addr = options.addr.replace(/\/+$/, '')
    this.#token = new RedactedSecret(options.token)
    this.#fetchImpl = options.fetchImpl
    this.#timeoutMs = options.timeoutMs ?? 10_000
  }

  /** Reads VAULT_ADDR and VAULT_TOKEN. Throws when either is missing. */
  static fromEnv(env: Record<string, string | undefined> = process.env): VaultClient {
    const addr = env.VAULT_ADDR
    const token = env.VAULT_TOKEN
    if (!addr || !token) {
      throw new VaultError('configure', undefined, 'VAULT_ADDR and VAULT_TOKEN must be set')
    }
    return new VaultClient({ addr, token })
  }

  toString(): string {
    return `VaultClient(addr=${this.#addr}, token=${REDACTED})`
  }

  [Symbol.for('nodejs.util.inspect.custom')](): string {
    return this.toString()
  }

  async getCredential(tenantId: string, ref: string): Promise<CredentialPayload> {
    const tenant = tenantSegment(tenantId)
    const credentialRef = parseCredentialRef(ref)
    return this.#kvRead('get_credential', `tenants/${tenant}/credentials/${credentialRef}`)
  }

  async getSessionState(tenantId: string, accountId: string): Promise<CredentialPayload> {
    const tenant = tenantSegment(tenantId)
    const account = accountSegment(accountId)
    return this.#kvRead('get_session_state', `tenants/${tenant}/browser-sessions/${account}`)
  }

  async putSessionState(
    tenantId: string,
    accountId: string,
    state: Record<string, unknown>
  ): Promise<void> {
    const tenant = tenantSegment(tenantId)
    const account = accountSegment(accountId)
    await this.#request(
      'put_session_state',
      'POST',
      `/v1/${KV_MOUNT}/data/tenants/${tenant}/browser-sessions/${account}`,
      {
        data: state,
      }
    )
  }

  async #kvRead(operation: string, relPath: string): Promise<CredentialPayload> {
    const body = await this.#request(operation, 'GET', `/v1/${KV_MOUNT}/data/${relPath}`)
    const parsed = kvReadBody.safeParse(body)
    if (!parsed.success) {
      throw new VaultError(operation, undefined, 'unexpected response shape')
    }
    return new RedactedSecret(parsed.data.data.data)
  }

  async #request(
    operation: string,
    method: 'GET' | 'POST',
    path: string,
    body?: unknown
  ): Promise<unknown> {
    const fetchFn = this.#fetchImpl ?? globalThis.fetch
    const headers: Record<string, string> = { 'X-Vault-Token': this.#token.reveal() }
    if (body !== undefined) {
      headers['Content-Type'] = 'application/json'
    }

    let response: Response
    try {
      response = await fetchFn(`${this.#addr}${path}`, {
        method,
        headers,
        body: body === undefined ? undefined : JSON.stringify(body),
        signal: AbortSignal.timeout(this.#timeoutMs),
      })
    } catch {
      throw new VaultError(operation, undefined, 'transport error')
    }

    if (response.status === 404) {
      throw new VaultNotFoundError(operation)
    }
    if (!response.ok) {
      throw new VaultError(operation, response.status)
    }
    try {
      return await response.json()
    } catch {
      throw new VaultError(operation, response.status, 'unexpected response')
    }
  }
}
