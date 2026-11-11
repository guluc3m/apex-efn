import { describe, expect, it } from 'vitest'

import type { Quote } from './personas.js'
import {
  createLlmPhraser,
  createPhraser,
  noopPhraser,
  pinsPrice,
  type FetchLike,
} from './phraser.js'

const SCRIPTED = 'Hello! Unit price is EUR 4.32, minimum order 1000 units.'
const PRICE: Quote = { minor: 432, currency: 'EUR', quantity: null }

function stubFetch(content: string, status = 200) {
  const calls: Array<{ url: string; init: RequestInit }> = []
  const impl: FetchLike = (url, init = {}) => {
    calls.push({ url, init })
    return Promise.resolve(
      new Response(JSON.stringify({ choices: [{ message: { content } }] }), {
        status,
        headers: { 'content-type': 'application/json' },
      })
    )
  }
  return { impl, calls }
}

function hangingFetch(): FetchLike {
  return (_url, init) =>
    new Promise<Response>((_resolve, reject) => {
      const signal = init?.signal
      if (!signal) return
      const fail = (): void => {
        const reason: unknown = signal.reason
        reject(reason instanceof Error ? reason : new Error('aborted'))
      }
      if (signal.aborted) return fail()
      signal.addEventListener('abort', fail, { once: true })
    })
}

interface ChatBody {
  model: string
  temperature: number
  messages: Array<{ role: string; content: string }>
}

function bodyOf(call: { init: RequestInit } | undefined): ChatBody {
  const raw = call?.init.body
  if (typeof raw !== 'string') throw new Error('request body was not a string')
  return JSON.parse(raw) as ChatBody
}

describe('pinsPrice', () => {
  it('accepts the same amount in the formats the personas use', () => {
    expect(pinsPrice(SCRIPTED, 'Hola, te lo dejo en €4.32 por unidad.', PRICE)).toBe(true)
    expect(pinsPrice(SCRIPTED, 'Precio: 4,32 EUR por unidad.', PRICE)).toBe(true)
    expect(pinsPrice(SCRIPTED, 'EUR 4.32 per unit, 1000 units minimum.', PRICE)).toBe(true)
    expect(pinsPrice(SCRIPTED, '  € 4.32  ', PRICE)).toBe(true)
  })

  it('rejects another amount or another currency', () => {
    expect(pinsPrice(SCRIPTED, 'Special price: EUR 4.00 per unit.', PRICE)).toBe(false)
    expect(pinsPrice(SCRIPTED, 'Special price: $4.32 per unit.', PRICE)).toBe(false)
    expect(pinsPrice(SCRIPTED, '€4.32 or €3.90 for 5000 units.', PRICE)).toBe(false)
  })

  it('rejects a rephrasing that drops the decided price', () => {
    expect(pinsPrice(SCRIPTED, 'Happy to help, what do you need?', PRICE)).toBe(false)
  })

  it('rejects empty or runaway text', () => {
    expect(pinsPrice(SCRIPTED, '   ', PRICE)).toBe(false)
    expect(pinsPrice(SCRIPTED, `${'x'.repeat(600)} €4.32`, PRICE)).toBe(false)
  })

  it('forbids any price when the persona stated none', () => {
    expect(pinsPrice('Let me check with my manager.', 'Déjame consultarlo.', null)).toBe(true)
    expect(pinsPrice('Let me check with my manager.', 'I can do EUR 4.32.', null)).toBe(false)
  })

  it('allows the prices the scripted reply already stated but no new ones', () => {
    const tiers = 'Our volume tiers are: 1-99 units: EUR 5.00; 100+ units: EUR 4.50.'
    const quote: Quote = { minor: 500, currency: 'EUR', quantity: null }
    expect(pinsPrice(tiers, 'Tiers: 1-99 at EUR 5.00, 100+ at EUR 4.50.', quote)).toBe(true)
    expect(pinsPrice(tiers, 'Tiers: 1-99 at EUR 5.00, 100+ at EUR 4.20.', quote)).toBe(false)
  })
})

describe('createPhraser', () => {
  it('is a no-op when SIM_LLM_URL is unset or blank', async () => {
    expect(createPhraser(undefined)).toBe(noopPhraser)
    expect(createPhraser('   ')).toBe(noopPhraser)
    await expect(noopPhraser.phrased(SCRIPTED, PRICE)).resolves.toBe(SCRIPTED)
  })
})

describe('createLlmPhraser', () => {
  it('posts an OpenAI-compatible chat completion and reads the message content', async () => {
    const { impl, calls } = stubFetch('  Hola, te lo dejo en €4.32.  ')
    const phraser = createLlmPhraser('http://stub.local/', { fetchImpl: impl })

    await expect(phraser.phrased(SCRIPTED, PRICE)).resolves.toBe('Hola, te lo dejo en €4.32.')

    const call = calls[0]
    expect(call?.url).toBe('http://stub.local/v1/chat/completions')
    const body = bodyOf(call)
    expect(body.model).toBe('seller')
    expect(body.temperature).toBe(0)
    expect(body.messages.map((m) => m.role)).toEqual(['system', 'user'])
    const system = body.messages[0]?.content ?? ''
    expect(system).toContain('one short chat message as the seller')
    expect(system).toContain('same language')
    expect(system).toContain('Keep the exact price (currency + amount)')
    expect(system).toContain('Never offer a different price')
    expect(system).toContain('never accept an order')
    expect(body.messages[1]?.content).toContain(SCRIPTED)
    expect(body.messages[1]?.content).toContain('EUR 4.32')
  })

  it('tells the stub not to invent a price when the persona stated none', async () => {
    const { impl, calls } = stubFetch('Déjame consultarlo con mi jefe.')
    const phraser = createLlmPhraser('http://stub.local', { fetchImpl: impl })

    await phraser.phrased('Let me check with my manager.', null)
    const body = bodyOf(calls[0])
    expect(body.messages[1]?.content).toContain('do not invent or mention any price')
  })

  it('throws on a non-2xx answer, malformed content or timeout', async () => {
    const failing = createLlmPhraser('http://stub.local', {
      fetchImpl: stubFetch('oops', 503).impl,
    })
    await expect(failing.phrased(SCRIPTED, PRICE)).rejects.toThrow('llm stub answered 503')

    const empty = createLlmPhraser('http://stub.local', { fetchImpl: stubFetch('   ').impl })
    await expect(empty.phrased(SCRIPTED, PRICE)).rejects.toThrow('no message content')

    const slow = createLlmPhraser('http://stub.local', {
      fetchImpl: hangingFetch(),
      timeoutMs: 20,
    })
    await expect(slow.phrased(SCRIPTED, PRICE)).rejects.toThrow()
  })
})
