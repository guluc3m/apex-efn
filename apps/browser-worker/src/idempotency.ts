import type { Redis } from 'ioredis'

import type { Clock } from './clock.js'
import { KeyedMutex } from './concurrency.js'
import { WorkerError } from './errors.js'
import { canonicalJson, sha256Hex } from './hash.js'

export interface StoredResponse {
  bodyHash: string
  status: number
  body: unknown
}

export interface IdempotentResponse<T> {
  status: number
  body: T
}

export interface IdempotencyStore {
  get(scope: string, key: string): Promise<StoredResponse | null>
  put(scope: string, key: string, value: StoredResponse, ttlSeconds: number): Promise<void>
}

const REDIS_PREFIX = 'bw:idem:'

function slotOf(scope: string, key: string): string {
  return sha256Hex(canonicalJson([scope, key]))
}

export function bodyHash(value: unknown): string {
  return sha256Hex(canonicalJson(value))
}

export function idempotencyConflict(): WorkerError {
  return new WorkerError('idempotency_conflict', 409, {
    detail: 'Idempotency-Key was already used with a different request body',
  })
}

export class InMemoryIdempotencyStore implements IdempotencyStore {
  private readonly entries = new Map<string, { value: StoredResponse; expiresAtMs: number }>()

  constructor(private readonly clock: Clock) {}

  get(scope: string, key: string): Promise<StoredResponse | null> {
    const slot = slotOf(scope, key)
    const entry = this.entries.get(slot)
    if (entry === undefined) {
      return Promise.resolve(null)
    }
    if (entry.expiresAtMs <= this.clock.now().getTime()) {
      this.entries.delete(slot)
      return Promise.resolve(null)
    }
    return Promise.resolve(entry.value)
  }

  put(scope: string, key: string, value: StoredResponse, ttlSeconds: number): Promise<void> {
    const nowMs = this.clock.now().getTime()
    const slot = slotOf(scope, key)
    const existing = this.entries.get(slot)
    if (existing !== undefined && existing.expiresAtMs > nowMs) {
      return Promise.resolve()
    }
    this.entries.set(slot, { value, expiresAtMs: nowMs + ttlSeconds * 1000 })
    return Promise.resolve()
  }
}

export class RedisIdempotencyStore implements IdempotencyStore {
  constructor(private readonly redis: Redis) {}

  async get(scope: string, key: string): Promise<StoredResponse | null> {
    const raw = await this.redis.get(REDIS_PREFIX + slotOf(scope, key))
    return raw === null ? null : (JSON.parse(raw) as StoredResponse)
  }

  async put(scope: string, key: string, value: StoredResponse, ttlSeconds: number): Promise<void> {
    await this.redis.set(
      REDIS_PREFIX + slotOf(scope, key),
      JSON.stringify(value),
      'EX',
      ttlSeconds,
      'NX'
    )
  }
}

const locks = new KeyedMutex()

/**
 * Runs `run` at most once per (scope, key). A replay with the same body returns the stored response; a
 * replay with a different body is a conflict. Calls with the same scope and key are serialised in this process.
 */
export function withIdempotency<T>(
  store: IdempotencyStore,
  scope: string,
  key: string,
  requestBody: unknown,
  ttlSeconds: number,
  run: () => Promise<IdempotentResponse<T>>
): Promise<IdempotentResponse<T>> {
  const hash = bodyHash(requestBody)
  return locks.run(`${scope}\n${key}`, async () => {
    const stored = await store.get(scope, key)
    if (stored !== null) {
      if (stored.bodyHash !== hash) {
        throw idempotencyConflict()
      }
      return { status: stored.status, body: stored.body as T }
    }
    const response = await run()
    await store.put(
      scope,
      key,
      { bodyHash: hash, status: response.status, body: response.body },
      ttlSeconds
    )
    return response
  })
}
