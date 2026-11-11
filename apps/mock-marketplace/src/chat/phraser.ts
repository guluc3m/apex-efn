import { formatMinor, parsePrices } from '../money.js'

import type { Quote } from './personas.js'

/**
 * Optional rephrasing of the scripted seller replies by an OpenAI-compatible LLM stub.
 *
 * The scripted personas own every decision (round, concession, price, flags). The model only ever gets to
 * rewrite the *wording* of the message, and the result is accepted only when it states exactly the price the
 * persona decided. Never let the model decide a number.
 */

export interface ChatPhraser {
  /** Rewrites `scripted` as one short seller message that keeps `price` (or states no price when null). */
  phrased(scripted: string, price: Quote | null): Promise<string>
}

/** Used when `SIM_LLM_URL` is unset: the scripted reply is sent unchanged. */
export const noopPhraser: ChatPhraser = {
  phrased: (scripted) => Promise.resolve(scripted),
}

/**
 * Operational timeout, not business config: rephrasing is cosmetic, so a slow stub must never delay the
 * chat. After this the scripted text is used.
 */
export const LLM_TIMEOUT_MS = 600

/** A reply far longer than any scripted line means the model ran away; the scripted text wins. */
const MAX_PHRASED_CHARS = 600

const SYSTEM_PROMPT = [
  'You rephrase messages that a marketplace seller sends in a simulated B2B chat.',
  'Write one short chat message as the seller, in the same language as the original message.',
  'Keep the exact price (currency + amount) that appears in the original message, copied unchanged.',
  'Never offer a different price, never add a second price and never accept an order.',
  'Reply with the message text only: no quotes, no explanations, no markdown.',
].join(' ')

export type FetchLike = (input: string, init?: RequestInit) => Promise<Response>

interface CompletionBody {
  choices?: Array<{ message?: { content?: unknown } }>
}

/** True when `text` states the persona's decision and adds no price the scripted text did not state. */
export function pinsPrice(scripted: string, candidate: string, quote: Quote | null): boolean {
  const text = candidate.trim()
  if (text.length === 0 || text.length > MAX_PHRASED_CHARS) return false
  const seen = parsePrices(text)
  // No price was decided: the model may not invent one.
  if (quote === null) return seen.length === 0
  const same = (p: { minor: number; currency: string | null }): boolean =>
    p.minor === quote.minor && p.currency === quote.currency
  // The decided price must be there...
  if (!seen.some(same)) return false
  // ...and every price the model writes must be the decided one or a price the scripted reply already had.
  const scriptedPrices = parsePrices(scripted)
  return seen.every(
    (p) => same(p) || scriptedPrices.some((s) => s.minor === p.minor && s.currency === p.currency)
  )
}

function userPrompt(scripted: string, price: Quote | null): string {
  const pin =
    price === null
      ? 'This message states no price: do not invent or mention any price or amount.'
      : `The only price you may state is ${price.currency} ${formatMinor(price.minor)}.`
  return `${pin}\nOriginal message:\n${scripted}`
}

export interface LlmPhraserOptions {
  timeoutMs?: number
  /** Stub scenario to force. `null` sends no header (a real provider, e.g. DeepSeek). */
  scenario?: string | null
  /** Bearer token for a real provider. Never logged, never in the payload. */
  apiKey?: string
  /** Injected in tests so no socket is ever opened. */
  fetchImpl?: FetchLike
  model?: string
}

/**
 * Chat phraser backed by an OpenAI-compatible stub (`POST {baseUrl}/v1/chat/completions`).
 * Any failure throws; `ChatEngine` then keeps the scripted text.
 */
export function createLlmPhraser(baseUrl: string, options: LlmPhraserOptions = {}): ChatPhraser {
  const endpoint = `${baseUrl.replace(/\/+$/, '')}/v1/chat/completions`
  const timeoutMs = options.timeoutMs ?? LLM_TIMEOUT_MS
  const fetchImpl = options.fetchImpl ?? fetch
  const model = options.model ?? 'seller'
  // `undefined` keeps the local stub default; `null` means a real provider and no header at all.
  const scenario = options.scenario === undefined ? 'sim-negotiation' : options.scenario

  return {
    async phrased(scripted: string, price: Quote | null): Promise<string> {
      const response = await fetchImpl(endpoint, {
        method: 'POST',
        headers: {
          'content-type': 'application/json',
          ...(scenario ? { 'x-stub-scenario': scenario } : {}),
          ...(options.apiKey ? { authorization: `Bearer ${options.apiKey}` } : {}),
        },
        body: JSON.stringify({
          model,
          messages: [
            { role: 'system', content: SYSTEM_PROMPT },
            { role: 'user', content: userPrompt(scripted, price) },
          ],
          temperature: 0,
        }),
        signal: AbortSignal.timeout(timeoutMs),
      })
      if (!response.ok) throw new Error(`llm stub answered ${response.status}`)
      const body = (await response.json()) as CompletionBody
      const content = body.choices?.[0]?.message?.content
      if (typeof content !== 'string' || content.trim().length === 0) {
        throw new Error('llm stub returned no message content')
      }
      return content.trim()
    },
  }
}

/** `SIM_LLM_URL` unset (or blank) keeps today's scripted wording. */
export function createPhraser(
  url: string | undefined,
  options: LlmPhraserOptions = {}
): ChatPhraser {
  return url === undefined || url.trim().length === 0 ? noopPhraser : createLlmPhraser(url, options)
}

/**
 * Reads the phraser configuration from the environment.
 *
 * With `SIM_LLM_API_KEY` (or `DEEPSEEK_API_KEY`) set, the endpoint is treated as a real provider: no stub
 * scenario header, no `seller` model name, and a timeout that a real request can meet. Without a key it is the
 * local stub the demo ships with. The key is read here and only here.
 */
export function phraserFromEnv(
  env: Record<string, string | number | undefined> = process.env
): ChatPhraser {
  const text = (key: string): string | undefined => {
    const value = env[key]
    return value === undefined ? undefined : String(value)
  }
  const apiKey = text('SIM_LLM_API_KEY') ?? text('DEEPSEEK_API_KEY')
  const model = text('SIM_LLM_MODEL') ?? (apiKey ? 'deepseek-chat' : 'seller')
  const scenario = text('SIM_LLM_SCENARIO') ?? (apiKey ? null : 'sim-negotiation')
  const timeoutMs = Number(text('SIM_LLM_TIMEOUT_MS') ?? (apiKey ? 8000 : LLM_TIMEOUT_MS))
  return createPhraser(text('SIM_LLM_URL'), {
    ...(apiKey ? { apiKey } : {}),
    ...(scenario === null ? { scenario: null } : { scenario }),
    ...(Number.isFinite(timeoutMs) && timeoutMs > 0 ? { timeoutMs } : {}),
    model,
  })
}
