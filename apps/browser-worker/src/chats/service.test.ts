import { createHash } from 'node:crypto'

import type {
  OpenChatRequest,
  SendChatMessageRequest,
} from '@apex/shared-types/contracts/browser-worker'
import { describe, expect, it } from 'vitest'

import { createHarness, START } from '../testing/harness.js'

const OPEN: OpenChatRequest = {
  tenant_id: 'tenant-1',
  mission_id: 'mission-1',
  trace_id: 'trace-1',
  negotiation_id: 'negotiation-1',
  platform: 'mock-b',
  account_id: 'account-1',
  platform_seller_id: 'seller-1',
  product_id: 'product-1',
}

const AGENT_SEND: SendChatMessageRequest = {
  text: 'Could you do 10% for 500 units?',
  sender: 'agent',
}

function humanSend(userId: string | null): SendChatMessageRequest {
  return { text: 'Taking over.', sender: 'human', user_id: userId }
}

async function openChat(h: ReturnType<typeof createHarness>, label = 'open-1') {
  const response = await h.chats.open(OPEN, `idem-key-${label}`.padEnd(20, '0'))
  return response.body
}

describe('ChatService.open', () => {
  it('opens once per Idempotency-Key and replays the same chat', async () => {
    const h = createHarness()
    const key = 'idem-key-open-0000001'
    const first = await h.chats.open(OPEN, key)
    const second = await h.chats.open(OPEN, key)
    expect(first.status).toBe(201)
    expect(second.body.chat_id).toBe(first.body.chat_id)
    expect(first.body.lock).toBeNull()
    expect(h.chatAdapter.opened).toHaveLength(1)
  })

  it('refuses a platform without chat support', async () => {
    const h = createHarness()
    await expect(
      h.chats.open({ ...OPEN, platform: 'mock-a' }, 'idem-key-nochat-0000001')
    ).rejects.toMatchObject({
      code: 'unknown_platform',
      status: 404,
      detail: 'platform has no chat',
    })
  })
})

describe('ChatService.get and read', () => {
  it('reports an unknown chat as 404', async () => {
    const h = createHarness()
    await expect(h.chats.get('missing')).rejects.toMatchObject({
      code: 'unknown_chat',
      status: 404,
    })
  })

  it('pages messages after after_seq and marks buyer messages sent through the worker', async () => {
    const h = createHarness()
    const chat = await openChat(h)
    h.chatAdapter.seedSellerMessage('Hello, what quantity?')
    await h.chats.send(chat.chat_id, AGENT_SEND, 'idem-key-send-00000001')
    h.chatAdapter.seedSellerMessage('Minimum is 1000.')

    const firstPage = await h.chats.read(chat.chat_id, 0, 2)
    expect(firstPage.messages.map((m) => [m.seq, m.role, m.sent_by])).toEqual([
      [1, 'seller', null],
      [2, 'buyer', 'agent'],
    ])
    expect(firstPage.last_seq).toBe(3)

    const rest = await h.chats.read(chat.chat_id, 2, 10)
    expect(rest.messages.map((m) => m.seq)).toEqual([3])
    expect(rest.messages[0]?.at).toBe(START)
  })
})

describe('ChatService.send', () => {
  it('sends an agent message and returns it as a buyer message', async () => {
    const h = createHarness()
    const chat = await openChat(h)
    const { status, body } = await h.chats.send(chat.chat_id, AGENT_SEND, 'idem-key-send-00000002')
    expect(status).toBe(201)
    expect(body).toMatchObject({ role: 'buyer', sent_by: 'agent', text: AGENT_SEND.text })
    expect(h.chatAdapter.sent).toHaveLength(1)
  })

  it('refuses an agent message while a human holds the lock, without calling the platform', async () => {
    const h = createHarness()
    const chat = await openChat(h)
    await h.chats.acquireLock(chat.chat_id, { user_id: 'user-1', ttl_seconds: 300 })
    await expect(
      h.chats.send(chat.chat_id, AGENT_SEND, 'idem-key-send-00000003')
    ).rejects.toMatchObject({
      code: 'chat_locked',
      status: 409,
    })
    expect(h.chatAdapter.sent).toHaveLength(0)
  })

  it('sends a human message from the lock holder', async () => {
    const h = createHarness()
    const chat = await openChat(h)
    await h.chats.acquireLock(chat.chat_id, { user_id: 'user-1', ttl_seconds: 300 })
    const { body } = await h.chats.send(chat.chat_id, humanSend('user-1'), 'idem-key-send-00000004')
    expect(body).toMatchObject({ sent_by: 'human' })
  })

  it('refuses a human message from another user or without a lock', async () => {
    const h = createHarness()
    const chat = await openChat(h)
    await expect(
      h.chats.send(chat.chat_id, humanSend('user-1'), 'idem-key-send-00000005')
    ).rejects.toMatchObject({
      code: 'not_lock_holder',
      status: 409,
    })
    await h.chats.acquireLock(chat.chat_id, { user_id: 'user-1', ttl_seconds: 300 })
    await expect(
      h.chats.send(chat.chat_id, humanSend('user-2'), 'idem-key-send-00000006')
    ).rejects.toMatchObject({
      code: 'not_lock_holder',
      status: 409,
    })
    expect(h.chatAdapter.sent).toHaveLength(0)
  })

  it('requires user_id for a human message', async () => {
    const h = createHarness()
    const chat = await openChat(h)
    await expect(
      h.chats.send(chat.chat_id, humanSend(null), 'idem-key-send-00000007')
    ).rejects.toMatchObject({
      code: 'validation_error',
      status: 422,
    })
  })

  it('sends at most once per Idempotency-Key', async () => {
    const h = createHarness()
    const chat = await openChat(h)
    const key = 'idem-key-send-00000008'
    const first = await h.chats.send(chat.chat_id, AGENT_SEND, key)
    const replay = await h.chats.send(chat.chat_id, AGENT_SEND, key)
    expect(replay).toEqual(first)
    expect(h.chatAdapter.sent).toHaveLength(1)
  })
})

describe('ChatService takeover lock', () => {
  it('refuses a lock held by another user and keeps acquired_at when the holder renews', async () => {
    const h = createHarness()
    const chat = await openChat(h)
    const first = await h.chats.acquireLock(chat.chat_id, { user_id: 'user-1', ttl_seconds: 60 })
    await expect(
      h.chats.acquireLock(chat.chat_id, { user_id: 'user-2', ttl_seconds: 60 })
    ).rejects.toMatchObject({
      code: 'lock_held',
      status: 409,
    })

    h.clock.advance(30_000)
    const renewed = await h.chats.acquireLock(chat.chat_id, { user_id: 'user-1', ttl_seconds: 120 })
    expect(renewed.acquired_at).toBe(first.acquired_at)
    expect(Date.parse(renewed.expires_at)).toBe(Date.parse(START) + 30_000 + 120_000)
  })

  it('lets the agent send again once the lock has expired', async () => {
    const h = createHarness()
    const chat = await openChat(h)
    await h.chats.acquireLock(chat.chat_id, { user_id: 'user-1', ttl_seconds: 60 })

    h.clock.advance(59_000)
    await expect(
      h.chats.send(chat.chat_id, AGENT_SEND, 'idem-key-send-00000009')
    ).rejects.toMatchObject({
      code: 'chat_locked',
    })

    h.clock.advance(1_000)
    await expect(h.chats.get(chat.chat_id)).resolves.toMatchObject({ lock: null })
    await expect(
      h.chats.send(chat.chat_id, AGENT_SEND, 'idem-key-send-00000010')
    ).resolves.toMatchObject({
      status: 201,
    })
  })

  it('refuses a release by a non-holder, and treats releasing a free lock as a no-op', async () => {
    const h = createHarness()
    const chat = await openChat(h)
    await expect(h.chats.releaseLock(chat.chat_id, 'user-1')).resolves.toBeUndefined()
    await h.chats.acquireLock(chat.chat_id, { user_id: 'user-1', ttl_seconds: 300 })
    await expect(h.chats.releaseLock(chat.chat_id, 'user-2')).rejects.toMatchObject({
      code: 'not_lock_holder',
      status: 409,
    })
    await h.chats.releaseLock(chat.chat_id, 'user-1')
    await expect(h.chats.get(chat.chat_id)).resolves.toMatchObject({ lock: null })
  })
})

describe('ChatService.screenshot', () => {
  it('stores the capture under a tenant and chat prefix with its sha256', async () => {
    const h = createHarness()
    const chat = await openChat(h)
    const { status, body } = await h.chats.screenshot(chat.chat_id, 'idem-key-shot-00000001')
    const bytes = new TextEncoder().encode(`PNG:pc-1`)

    expect(status).toBe(201)
    expect(body.screenshot_ref.startsWith(`screenshots/tenant-1/${chat.chat_id}/`)).toBe(true)
    expect(body.sha256).toBe(createHash('sha256').update(bytes).digest('hex'))
    expect(h.artifacts.objects.get(body.screenshot_ref)).toEqual(bytes)
  })
})
