import type { Clock } from '../clock.js'
import type { Catalog, PersonaId, PlatformId, Product, Seller } from '../fixtures/schema.js'
import { createRng, hashString, type Rng } from '../rng.js'

import {
  initialState,
  respond,
  type PersonaFlag,
  type PersonaState,
  type Quote,
} from './personas.js'

export type MessageRole = 'buyer' | 'seller'

export interface ChatMessage {
  seq: number
  role: MessageRole
  text: string
  at: string
}

export interface Chat {
  id: string
  platform: PlatformId
  sellerId: string
  productId: string
  messages: ChatMessage[]
  state: PersonaState
  rng: Rng
}

export class ChatError extends Error {
  constructor(
    readonly code:
      'unknown_seller' | 'unknown_product' | 'unknown_chat' | 'wrong_platform' | 'empty_message',
    message: string
  ) {
    super(message)
  }
}

export interface ChatSnapshot {
  id: string
  platform: PlatformId
  sellerId: string
  productId: string
  persona: PersonaId
  round: number
  messages: ChatMessage[]
  lastQuote: Quote | null
  agreed: Quote | null
  floor: { minor: number; currency: string }
  flags: PersonaFlag[]
}

/**
 * In-memory chat store. Deterministic: chat ids are sequential and each chat's RNG is derived from the
 * global seed plus the chat id, so the same seed and the same buyer messages give the same transcript.
 */
export class ChatEngine {
  private chats = new Map<string, Chat>()
  private counter = 0
  private overrides = new Map<string, PersonaId>()

  constructor(
    private readonly catalog: Catalog,
    private readonly clock: Clock,
    private seed: number
  ) {}

  reset(seed?: number): void {
    if (seed !== undefined) this.seed = seed
    this.chats.clear()
    this.overrides.clear()
    this.counter = 0
  }

  get currentSeed(): number {
    return this.seed
  }

  setPersona(sellerId: string, persona: PersonaId): void {
    this.seller(sellerId)
    this.overrides.set(sellerId, persona)
  }

  setChatPersona(chatId: string, persona: PersonaId): void {
    const chat = this.get(chatId)
    const product = this.product(chat.productId)
    const next = initialState(persona, product)
    next.round = chat.state.round
    chat.state = next
  }

  personaFor(sellerId: string): PersonaId {
    return this.overrides.get(sellerId) ?? this.seller(sellerId).persona
  }

  open(platform: PlatformId, sellerId: string, productId: string): Chat {
    const seller = this.seller(sellerId)
    const product = this.product(productId)
    if (seller.platform !== platform || product.platform !== platform) {
      throw new ChatError('wrong_platform', `seller or product is not on ${platform}`)
    }
    if (product.sellerId !== seller.id)
      throw new ChatError('unknown_product', 'product is not sold by this seller')
    this.counter += 1
    const id = `chat-${platform}-${String(this.counter).padStart(4, '0')}`
    const chat: Chat = {
      id,
      platform,
      sellerId,
      productId,
      messages: [],
      state: initialState(this.personaFor(sellerId), product),
      rng: createRng(hashString(`${this.seed}:${id}`)),
    }
    this.chats.set(id, chat)
    return chat
  }

  get(chatId: string): Chat {
    const chat = this.chats.get(chatId)
    if (!chat) throw new ChatError('unknown_chat', `unknown chat ${chatId}`)
    return chat
  }

  /** Appends the buyer message and the seller reply. Returns both messages. */
  send(chatId: string, text: string): ChatMessage[] {
    const chat = this.get(chatId)
    const clean = text.trim()
    if (clean.length === 0) throw new ChatError('empty_message', 'message is empty')
    const buyer = this.append(chat, 'buyer', clean)
    const reply = respond(chat.state, clean, this.product(chat.productId), chat.rng)
    const seller = this.append(chat, 'seller', reply.text)
    return [buyer, seller]
  }

  read(chatId: string, afterSeq = 0): ChatMessage[] {
    return this.get(chatId).messages.filter((m) => m.seq > afterSeq)
  }

  snapshot(chatId: string): ChatSnapshot {
    const c = this.get(chatId)
    return {
      id: c.id,
      platform: c.platform,
      sellerId: c.sellerId,
      productId: c.productId,
      persona: c.state.persona,
      round: c.state.round,
      messages: [...c.messages],
      lastQuote: c.state.lastQuote,
      agreed: c.state.agreed,
      floor: { minor: c.state.floorMinor, currency: c.state.currency },
      flags: [...c.state.flags],
    }
  }

  list(): ChatSnapshot[] {
    return [...this.chats.keys()].map((id) => this.snapshot(id))
  }

  private append(chat: Chat, role: MessageRole, text: string): ChatMessage {
    const msg: ChatMessage = {
      seq: chat.messages.length + 1,
      role,
      text,
      at: this.clock.now().toISOString(),
    }
    chat.messages.push(msg)
    return msg
  }

  private seller(id: string): Seller {
    const s = this.catalog.sellers.find((x) => x.id === id)
    if (!s) throw new ChatError('unknown_seller', `unknown seller ${id}`)
    return s
  }

  private product(id: string): Product {
    const p = this.catalog.products.find((x) => x.id === id)
    if (!p) throw new ChatError('unknown_product', `unknown product ${id}`)
    return p
  }
}
