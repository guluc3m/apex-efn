/**
 * Per-account browser sessions (D5-02b).
 *
 * The worker never invents a login: it restores the cookies and origin storage an account already has, persists
 * them again after use, and stops using an account the platform rejected. Cookies live **only** in memory here and
 * in Vault at rest (`tenants/<tenant>/browser-sessions/<account>`, written by the DEV-1 client); they never reach
 * the orchestrator, the LLM or a log line.
 *
 * Re-authentication is human-assisted and needs no endpoint: when the platform invalidates a session the document
 * is marked `needs_reauth`, and a human writes a fresh document into Vault (same path, `needs_reauth: false`) with
 * whatever tooling operations already has. The next `restore` picks it up. That keeps credentials out of this API
 * entirely, which is the rule for the whole worker.
 */

import { z } from 'zod'

import type { Clock } from '../clock.js'
import { WorkerError } from '../errors.js'
import type { VaultClient } from '../platform/vault.js'

export interface StoredCookie {
  name: string
  value: string
  domain: string
  path: string
  expires?: number
  httpOnly?: boolean
  secure?: boolean
  sameSite?: 'Strict' | 'Lax' | 'None'
}

export interface StorageItem {
  name: string
  value: string
}

export interface StoredOrigin {
  origin: string
  items: StorageItem[]
}

/** One account's saved session. Treat it as a secret: never log it, never put it in an error message. */
export interface StoredSession {
  /** Bumped on every write. A human refresh is just a normal write. */
  version: number
  cookies: StoredCookie[]
  origins: StoredOrigin[]
  updatedAt: string
  /** Set when the platform rejected the session; a human write clears it. */
  needsReauth: boolean
  reason: string | null
}

export type RestoreResult = 'restored' | 'missing' | 'needs_reauth'

/** What a page must offer for the manager to save and restore a session. The Puppeteer page implements it. */
export interface SessionSurface {
  cookies(): Promise<StoredCookie[]>
  setCookies(cookies: StoredCookie[]): Promise<void>
  storage(origin: string): Promise<StorageItem[]>
  setStorage(origin: string, items: StorageItem[]): Promise<void>
}

export interface SessionStore {
  load(tenantId: string, accountId: string): Promise<StoredSession | null>
  save(tenantId: string, accountId: string, session: StoredSession): Promise<void>
}

const cookieSchema = z.object({
  name: z.string().min(1),
  value: z.string(),
  domain: z.string().min(1),
  path: z.string().min(1),
  expires: z.number().optional(),
  httpOnly: z.boolean().optional(),
  secure: z.boolean().optional(),
  sameSite: z.enum(['Strict', 'Lax', 'None']).optional(),
})

const storedSessionSchema = z.object({
  version: z.number().int().nonnegative(),
  cookies: z.array(cookieSchema),
  origins: z.array(
    z.object({
      origin: z.string().url(),
      items: z.array(z.object({ name: z.string(), value: z.string() })),
    })
  ),
  updatedAt: z.string(),
  needsReauth: z.boolean(),
  reason: z.string().nullable(),
})

/**
 * Session store backed by Vault KV v2 through the DEV-1 client.
 *
 * A missing document is `null`, not an error: a new account has no session yet. A document that does not match
 * the schema is a hard failure, because silently starting from empty would look logged-in-until-it-isn't.
 */
export class VaultSessionStore implements SessionStore {
  constructor(private readonly vault: VaultClient) {}

  async load(tenantId: string, accountId: string): Promise<StoredSession | null> {
    let payload: Record<string, unknown>
    try {
      payload = (await this.vault.getSessionState(tenantId, accountId)).reveal()
    } catch (error) {
      if (isNotFound(error)) {
        return null
      }
      throw error
    }
    const parsed = storedSessionSchema.safeParse(payload)
    if (!parsed.success) {
      throw new WorkerError('session_invalid', 409, {
        detail: 'stored browser session does not match the expected shape',
      })
    }
    return parsed.data
  }

  async save(tenantId: string, accountId: string, session: StoredSession): Promise<void> {
    await this.vault.putSessionState(tenantId, accountId, session as unknown as Record<string, unknown>)
  }
}

function isNotFound(error: unknown): boolean {
  return (
    typeof error === 'object' &&
    error !== null &&
    'status' in error &&
    (error as { status?: number }).status === 404
  )
}

export class SessionManager {
  constructor(
    private readonly store: SessionStore,
    private readonly clock: Clock
  ) {}

  /**
   * Applies the stored session to a page.
   *
   * Returns `missing` when the account has never logged in and `needs_reauth` when the platform rejected the
   * session, so the caller can answer `session_invalid` with the right detail instead of guessing.
   */
  async restore(
    surface: SessionSurface,
    tenantId: string,
    accountId: string
  ): Promise<RestoreResult> {
    const session = await this.store.load(tenantId, accountId)
    if (session === null) {
      return 'missing'
    }
    if (session.needsReauth) {
      return 'needs_reauth'
    }
    if (session.cookies.length > 0) {
      await surface.setCookies(session.cookies)
    }
    for (const origin of session.origins) {
      await surface.setStorage(origin.origin, origin.items)
    }
    return 'restored'
  }

  /** Reads the session back from the page and stores it, bumping the version. */
  async persist(
    surface: SessionSurface,
    tenantId: string,
    accountId: string,
    previous: StoredSession | null = null
  ): Promise<StoredSession> {
    const base = previous ?? (await this.store.load(tenantId, accountId))
    const cookies = await surface.cookies()
    const origins: StoredOrigin[] = []
    for (const origin of new Set(base?.origins.map((entry) => entry.origin) ?? [])) {
      origins.push({ origin, items: await surface.storage(origin) })
    }
    const session: StoredSession = {
      version: (base?.version ?? 0) + 1,
      cookies,
      origins,
      updatedAt: this.clock.now().toISOString(),
      needsReauth: false,
      reason: null,
    }
    await this.store.save(tenantId, accountId, session)
    return session
  }

  /** Marks the session unusable after the platform rejected it. The cookies are kept for forensics, not reused. */
  async invalidate(
    tenantId: string,
    accountId: string,
    reason: string
  ): Promise<StoredSession> {
    const session = await this.store.load(tenantId, accountId)
    const marked: StoredSession = {
      version: session?.version ?? 0,
      cookies: session?.cookies ?? [],
      origins: session?.origins ?? [],
      updatedAt: this.clock.now().toISOString(),
      needsReauth: true,
      reason,
    }
    await this.store.save(tenantId, accountId, marked)
    return marked
  }
}

/** Turns a restore result into the error the API should answer, if any. */
export function sessionErrorFor(result: RestoreResult): WorkerError | null {
  if (result === 'restored') {
    return null
  }
  return new WorkerError('session_invalid', 409, {
    detail:
      result === 'missing'
        ? 'no stored session for this account'
        : 'session rejected by the platform; a human has to refresh it in Vault',
  })
}
