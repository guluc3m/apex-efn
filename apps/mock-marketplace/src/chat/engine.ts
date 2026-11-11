import type { Clock } from '../clock.js'
import type { Catalog, PersonaId, PlatformId, Product, Seller } from '../fixtures/schema.js'
import { createRng, hashString, type Rng } from '../rng.js'

import {
  initialState,
  respond,
  type PersonaFlag,
  type PersonaReply,
  type PersonaState,
  type Quote,
} from './personas.js'
import { noopPhraser, pinsPrice, type ChatPhraser } from './phraser.js'

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
/** Seller messages that close the deal: sent exactly as scripted. */
const CONFIRMATION_RE = /confirmed in writing|确认|confirmad[oa]s?\b|we accept the summary/i

export class ChatEngine {
  private chats = new Map<string, Chat>()
  private counter = 0
  private overrides = new Map<string, PersonaId>()

  constructor(
    private readonly catalog: Catalog,
    private readonly clock: Clock,
    private seed: number,
    /** Optional wording-only rephraser (`SIM_LLM_URL`). Absent or unset: scripted text, as before. */
    private readonly phraser?: ChatPhraser
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

  /**
   * Appends the buyer message and the seller reply. Returns both messages.
   *
   * `phraser` overrides the engine's own phraser for this call only (the orchestrator sim sends a
   * per-request provider configuration). It is a parameter, never stored, so concurrent chats cannot
   * see each other's provider or key.
   *
   * Without a phraser (unset, or the no-op phraser `SIM_LLM_URL` unset builds) the whole call still runs
   * synchronously, so the appended order, `seq` and `at` are exactly as before. With a real phraser, only
   * the seller's wording is awaited — state and numbers are already decided by `respond`.
   */
  async send(chatId: string, text: string, phraser?: ChatPhraser): Promise<ChatMessage[]> {
    const chat = this.get(chatId)
    const clean = text.trim()
    if (clean.length === 0) throw new ChatError('empty_message', 'message is empty')
    const buyer = this.append(chat, 'buyer', clean)
    const reply = respond(chat.state, clean, this.product(chat.productId), chat.rng)
    const active = phraser ?? this.phraser
    // A persona that has closed the deal answers with the written confirmation: never reworded.
    const sellerText =
      active === undefined || active === noopPhraser || chat.state.agreed !== null
        ? reply.text
        : await this.rephrase(reply, active)
    const seller = this.append(chat, 'seller', sellerText)
    return [buyer, seller]
  }

  /** Rephrasing is cosmetic: anything unexpected (error, timeout, price drift) keeps the scripted text. */
  private async rephrase(reply: PersonaReply, phraser: ChatPhraser): Promise<string> {
    // A written confirmation is the sentence the buyer relies on; it is never reworded by a model.
    if (CONFIRMATION_RE.test(reply.text)) return reply.text
    try {
      const candidate = await phraser.phrased(reply.text, reply.quote)
      return pinsPrice(reply.text, candidate, reply.quote) ? candidate.trim() : reply.text
    } catch {
      return reply.text
    }
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
