import type {
  AcquireChatLockRequest,
  Chat,
  ChatLock,
  ChatMessage,
  ChatMessagePage,
  ChatScreenshot,
  OpenChatRequest,
  SendChatMessageRequest,
} from '@apex/shared-types/contracts/browser-worker'

import type { AdapterRegistry, ChatAdapter } from '../adapters/index.js'
import type { ArtifactStore } from '../artifacts.js'
import type { Clock } from '../clock.js'
import { KeyedMutex } from '../concurrency.js'
import { WorkerError } from '../errors.js'
import { sha256Hex } from '../hash.js'
import { withIdempotency, type IdempotencyStore, type IdempotentResponse } from '../idempotency.js'

import type { ChatRecord, ChatStore } from './store.js'

export interface ChatServiceOptions {
  registry: AdapterRegistry
  store: ChatStore
  idempotency: IdempotencyStore
  artifacts: ArtifactStore
  clock: Clock
  newId: () => string
  idempotencyTtlSeconds: number
}

export class ChatService {
  private readonly mutex = new KeyedMutex()

  constructor(private readonly options: ChatServiceOptions) {}

  open(request: OpenChatRequest, key: string): Promise<IdempotentResponse<Chat>> {
    return withIdempotency(
      this.options.idempotency,
      'open-chat',
      key,
      request,
      this.ttl(),
      async () => {
        const adapter = this.chatAdapterFor(request.platform)
        const opened = await adapter.open({
          accountId: request.account_id,
          platformSellerId: request.platform_seller_id,
          productId: request.product_id,
        })
        const record: ChatRecord = {
          chat_id: this.options.newId(),
          tenant_id: request.tenant_id,
          negotiation_id: request.negotiation_id,
          platform: request.platform,
          account_id: request.account_id,
          platform_seller_id: request.platform_seller_id,
          product_id: request.product_id,
          opened_at: this.now().toISOString(),
          lock: null,
          platformChatId: opened.platformChatId,
          sentBy: {},
        }
        await this.options.store.put(record)
        return { status: 201, body: toChat(record, this.now()) }
      }
    )
  }

  async get(chatId: string): Promise<Chat> {
    const record = await this.require(chatId)
    return toChat(record, this.now())
  }

  async read(chatId: string, afterSeq: number, limit: number): Promise<ChatMessagePage> {
    const record = await this.require(chatId)
    const adapter = this.chatAdapterFor(record.platform)
    const thread = await adapter.read(record.platformChatId, afterSeq)
    const lastSeq = thread.reduce((highest, message) => Math.max(highest, message.seq), afterSeq)
    const messages = thread
      .filter((message) => message.seq > afterSeq)
      .sort((a, b) => a.seq - b.seq)
      .slice(0, limit)
      .map((message): ChatMessage => ({
        seq: message.seq,
        role: message.role,
        text: message.text,
        at: message.at.toISOString(),
        sent_by: message.role === 'buyer' ? (record.sentBy[String(message.seq)] ?? null) : null,
      }))
    return { chat_id: chatId, messages, last_seq: lastSeq }
  }

  send(
    chatId: string,
    request: SendChatMessageRequest,
    key: string
  ): Promise<IdempotentResponse<ChatMessage>> {
    return withIdempotency(
      this.options.idempotency,
      `send:${chatId}`,
      key,
      request,
      this.ttl(),
      () =>
        this.mutex.run(chatId, async (): Promise<IdempotentResponse<ChatMessage>> => {
          const record = await this.require(chatId)
          this.assertMaySend(record, request)
          const adapter = this.chatAdapterFor(record.platform)
          const sent = await adapter.send(record.platformChatId, request.text)
          record.sentBy[String(sent.platformSeq)] = request.sender
          await this.options.store.put(record)
          return {
            status: 201,
            body: {
              seq: sent.platformSeq,
              role: 'buyer',
              text: request.text,
              at: sent.at.toISOString(),
              sent_by: request.sender,
            },
          }
        })
    )
  }

  acquireLock(chatId: string, request: AcquireChatLockRequest): Promise<ChatLock> {
    return this.mutex.run(chatId, async () => {
      const record = await this.require(chatId)
      const now = this.now()
      const current = activeLock(record, now)
      if (current !== null && current.user_id !== request.user_id) {
        throw new WorkerError('lock_held', 409)
      }
      const lock: ChatLock = {
        holder: 'human',
        user_id: request.user_id,
        acquired_at: current?.acquired_at ?? now.toISOString(),
        expires_at: new Date(now.getTime() + request.ttl_seconds * 1000).toISOString(),
      }
      record.lock = lock
      await this.options.store.put(record)
      return lock
    })
  }

  releaseLock(chatId: string, userId: string): Promise<void> {
    return this.mutex.run(chatId, async () => {
      const record = await this.require(chatId)
      const current = activeLock(record, this.now())
      if (current === null) {
        return
      }
      if (current.user_id !== userId) {
        throw new WorkerError('not_lock_holder', 409)
      }
      record.lock = null
      await this.options.store.put(record)
    })
  }

  screenshot(chatId: string, key: string): Promise<IdempotentResponse<ChatScreenshot>> {
    return withIdempotency(
      this.options.idempotency,
      `shot:${chatId}`,
      key,
      {},
      this.ttl(),
      async () => {
        const record = await this.require(chatId)
        const adapter = this.chatAdapterFor(record.platform)
        const bytes = await adapter.screenshot(record.platformChatId)
        const ref = `screenshots/${record.tenant_id}/${chatId}/${this.options.newId()}.png`
        await this.options.artifacts.put(ref, bytes)
        return {
          status: 201,
          body: {
            screenshot_ref: ref,
            sha256: sha256Hex(bytes),
            captured_at: this.now().toISOString(),
          },
        }
      }
    )
  }

  private assertMaySend(record: ChatRecord, request: SendChatMessageRequest): void {
    const lock = activeLock(record, this.now())
    if (request.sender === 'agent') {
      if (lock !== null) {
        throw new WorkerError('chat_locked', 409)
      }
      return
    }
    if (!request.user_id) {
      throw new WorkerError('validation_error', 422, {
        detail: 'user_id is required for human sends',
      })
    }
    if (lock?.user_id !== request.user_id) {
      throw new WorkerError('not_lock_holder', 409)
    }
  }

  private chatAdapterFor(platform: string): ChatAdapter {
    const adapter = this.options.registry.require(platform)
    if (adapter.chat === undefined) {
      throw new WorkerError('unknown_platform', 404, { detail: 'platform has no chat' })
    }
    return adapter.chat
  }

  private async require(chatId: string): Promise<ChatRecord> {
    const record = await this.options.store.get(chatId)
    if (record === null) {
      throw new WorkerError('unknown_chat', 404)
    }
    return record
  }

  private now(): Date {
    return this.options.clock.now()
  }

  private ttl(): number {
    return this.options.idempotencyTtlSeconds
  }
}

function activeLock(record: ChatRecord, now: Date): ChatLock | null {
  if (record.lock === null) {
    return null
  }
  return Date.parse(record.lock.expires_at) > now.getTime() ? record.lock : null
}

function toChat(record: ChatRecord, now: Date): Chat {
  return {
    chat_id: record.chat_id,
    tenant_id: record.tenant_id,
    negotiation_id: record.negotiation_id,
    platform: record.platform,
    account_id: record.account_id,
    platform_seller_id: record.platform_seller_id,
    product_id: record.product_id,
    opened_at: record.opened_at,
    lock: activeLock(record, now),
  }
}
