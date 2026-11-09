import { AdapterRegistry } from '../adapters/index.js'
import { InMemoryArtifactStore } from '../artifacts.js'
import { ChatService } from '../chats/service.js'
import { InMemoryChatStore } from '../chats/store.js'
import { buildServer } from '../http/server.js'
import { InMemoryIdempotencyStore } from '../idempotency.js'
import { InMemoryJobService } from '../jobs/service.js'
import { StaticFlags } from '../platform/flags.js'

import { FakeChatAdapter, FakePlatformAdapter, FixedClock } from './fakes.js'

export const TOKEN = 'test-service-token-'.padEnd(40, 'x')
export const START = '2026-11-09T10:00:00.000Z'

export function createHarness() {
  const clock = new FixedClock(START)
  const flags = new StaticFlags({
    'platform.mock-a.enabled': true,
    'platform.mock-b.enabled': true,
    'platform.mock-c.enabled': false,
  })
  let counter = 0
  const newId = (): string => {
    counter += 1
    return `id-${counter}`
  }
  const chatAdapter = new FakeChatAdapter(clock)
  const sourcing = new FakePlatformAdapter('mock-a', 'http')
  const chatting = new FakePlatformAdapter('mock-b', 'browser', chatAdapter)
  const disabled = new FakePlatformAdapter('mock-c', 'http')
  const registry = new AdapterRegistry([sourcing, chatting, disabled], flags)
  const jobs = new InMemoryJobService(registry, clock, newId)
  const artifacts = new InMemoryArtifactStore()
  const chats = new ChatService({
    registry,
    store: new InMemoryChatStore(),
    idempotency: new InMemoryIdempotencyStore(clock),
    artifacts,
    clock,
    newId,
    idempotencyTtlSeconds: 86400,
  })
  const app = buildServer({ token: TOKEN, jobs, chats, registry })
  return { app, clock, registry, jobs, chats, artifacts, sourcing, chatting, disabled, chatAdapter }
}

export type Harness = ReturnType<typeof createHarness>

export function bearer(token: string = TOKEN): Record<string, string> {
  return { authorization: `Bearer ${token}` }
}

export function idempotencyKey(label: string): Record<string, string> {
  return { 'idempotency-key': `idem-key-${label}`.padEnd(20, '0') }
}
