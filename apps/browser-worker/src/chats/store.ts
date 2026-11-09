import type { Chat, ChatSender } from '@apex/shared-types/contracts/browser-worker'
import type { Redis } from 'ioredis'

export type ChatRecord = Chat & {
  platformChatId: string
  /** Who sent each buyer message through this worker, keyed by the platform sequence number. */
  sentBy: Record<string, ChatSender>
}

export interface ChatStore {
  get(chatId: string): Promise<ChatRecord | null>
  put(record: ChatRecord): Promise<void>
}

export class InMemoryChatStore implements ChatStore {
  private readonly records = new Map<string, string>()

  get(chatId: string): Promise<ChatRecord | null> {
    const raw = this.records.get(chatId)
    return Promise.resolve(raw === undefined ? null : (JSON.parse(raw) as ChatRecord))
  }

  put(record: ChatRecord): Promise<void> {
    this.records.set(record.chat_id, JSON.stringify(record))
    return Promise.resolve()
  }
}

function chatKey(chatId: string): string {
  return `bw:chat:${chatId}`
}

export class RedisChatStore implements ChatStore {
  constructor(private readonly redis: Redis) {}

  async get(chatId: string): Promise<ChatRecord | null> {
    const raw = await this.redis.get(chatKey(chatId))
    return raw === null ? null : (JSON.parse(raw) as ChatRecord)
  }

  async put(record: ChatRecord): Promise<void> {
    await this.redis.set(chatKey(record.chat_id), JSON.stringify(record))
  }
}
