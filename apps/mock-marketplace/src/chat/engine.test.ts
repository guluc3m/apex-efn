import { describe, expect, it } from 'vitest'

import { steppingClock } from '../clock.js'
import { buildServer, type MockMarketplace } from '../server.js'

import type { ChatSnapshot } from './engine.js'
import { noopPhraser, type ChatPhraser } from './phraser.js'

const FIXED = new Date('2026-11-01T09:00:00.000Z')
const BUYER_LINE = 'Hello, we need 1000 units. What is your price?'
const SCRIPTED_FIRST = 'Hello! Unit price is EUR 4.32, minimum order 1000 units.'

function server(phraser?: ChatPhraser): MockMarketplace {
  return buildServer({ clock: steppingClock(FIXED), seed: 42, phraser })
}

async function firstExchange(phraser?: ChatPhraser) {
  const market = server(phraser)
  const chat = market.chats.open('mock-c', 'c-solid-supplier', 'c-gloves-01')
  const messages = await market.chats.send(chat.id, BUYER_LINE)
  return { market, snapshot: market.chats.snapshot(chat.id), messages }
}

function sellerText(snapshot: ChatSnapshot): string | undefined {
  return snapshot.messages.find((m) => m.role === 'seller')?.text
}

describe('ChatEngine without a phraser', () => {
  it('keeps the scripted wording and appends synchronously, as before', async () => {
    const { app, chats } = server()
    const chat = chats.open('mock-c', 'c-solid-supplier', 'c-gloves-01')

    const pending = chats.send(chat.id, BUYER_LINE)
    // No phraser is configured: both messages are already there before the promise is awaited.
    expect(chats.snapshot(chat.id).messages).toHaveLength(2)
    const messages = await pending

    expect(messages.map((m) => m.seq)).toEqual([1, 2])
    expect(messages.map((m) => m.at)).toEqual([
      FIXED.toISOString(),
      new Date(FIXED.getTime() + 1000).toISOString(),
    ])
    expect(sellerText(chats.snapshot(chat.id))).toBe(SCRIPTED_FIRST)
    await app.close()
  })

  it('is also synchronous with the no-op phraser that an unset SIM_LLM_URL builds', async () => {
    const { app, chats } = server(noopPhraser)
    const chat = chats.open('mock-c', 'c-solid-supplier', 'c-gloves-01')

    const pending = chats.send(chat.id, BUYER_LINE)
    expect(chats.snapshot(chat.id).messages).toHaveLength(2)
    await pending
    expect(sellerText(chats.snapshot(chat.id))).toBe(SCRIPTED_FIRST)
    await app.close()
  })
})

describe('ChatEngine with an injected phraser', () => {
  it('passes the scripted reply and the decided price to the phraser', async () => {
    const seen: Array<{ scripted: string; price: unknown }> = []
    const phraser: ChatPhraser = {
      phrased: (scripted, price) => {
        seen.push({ scripted, price })
        return Promise.resolve('Hola, te lo dejo en €4.32 por unidad.')
      },
    }

    const { market } = await firstExchange(phraser)
    expect(seen).toEqual([
      { scripted: SCRIPTED_FIRST, price: { minor: 432, currency: 'EUR', quantity: 1000 } },
    ])
    await market.app.close()
  })

  it('uses a rephrasing that keeps the same price', async () => {
    const { market, snapshot } = await firstExchange({
      phrased: () => Promise.resolve('Hola, te lo dejo en €4.32 por unidad.'),
    })

    expect(sellerText(snapshot)).toBe('Hola, te lo dejo en €4.32 por unidad.')
    expect(snapshot.lastQuote).toEqual({ minor: 432, currency: 'EUR', quantity: 1000 })
    expect(snapshot.round).toBe(1)
    await market.app.close()
  })

  it('accepts alternative formatting of the same amount', async () => {
    const { market, snapshot } = await firstExchange({
      phrased: () => Promise.resolve('  Precio: 4,32 EUR por unidad.  '),
    })

    expect(sellerText(snapshot)).toBe('Precio: 4,32 EUR por unidad.')
    await market.app.close()
  })

  it('rejects a rephrasing that changes the price and keeps the scripted text', async () => {
    const { market, snapshot } = await firstExchange({
      phrased: () => Promise.resolve('Special price for you: EUR 4.00 per unit.'),
    })

    expect(sellerText(snapshot)).toBe(SCRIPTED_FIRST)
    expect(snapshot.lastQuote).toEqual({ minor: 432, currency: 'EUR', quantity: 1000 })
    await market.app.close()
  })

  it('rejects a rephrasing that adds a second price', async () => {
    const { market, snapshot } = await firstExchange({
      phrased: () => Promise.resolve('EUR 4.32 per unit, or EUR 3.90 if you take 5000 units.'),
    })

    expect(sellerText(snapshot)).toBe(SCRIPTED_FIRST)
    await market.app.close()
  })

  it('rejects a rephrasing that drops the decided price', async () => {
    const { market, snapshot } = await firstExchange({
      phrased: () => Promise.resolve('Encantados de atenderte, dime qué necesitas.'),
    })

    expect(sellerText(snapshot)).toBe(SCRIPTED_FIRST)
    await market.app.close()
  })

  it('rejects a rephrasing that invents a price when the persona stated none', async () => {
    const market = server({
      phrased: () => Promise.resolve('Claro, te lo dejo en EUR 4.10 por unidad.'),
    })
    const chat = market.chats.open('mock-c', 'c-new-shop', 'c-gloves-04')
    await market.chats.send(chat.id, BUYER_LINE)
    const snapshot = market.chats.snapshot(chat.id)

    expect(snapshot.lastQuote).toBeNull()
    expect(sellerText(snapshot)).not.toContain('4.10')
    await market.app.close()
  })

  it('keeps the scripted text when the phraser throws', async () => {
    const { market, snapshot } = await firstExchange({
      phrased: () => Promise.reject(new Error('stub exploded')),
    })

    expect(sellerText(snapshot)).toBe(SCRIPTED_FIRST)
    await market.app.close()
  })

  it('keeps the scripted text when the phraser times out', async () => {
    const { market, snapshot } = await firstExchange({
      phrased: () => Promise.reject(new DOMException('timed out', 'TimeoutError')),
    })

    expect(sellerText(snapshot)).toBe(SCRIPTED_FIRST)
    await market.app.close()
  })

  it('keeps the scripted text when the phraser returns empty text', async () => {
    const { market, snapshot } = await firstExchange({ phrased: () => Promise.resolve('   ') })

    expect(sellerText(snapshot)).toBe(SCRIPTED_FIRST)
    await market.app.close()
  })
})

describe('mock-c thread endpoint with a phraser', () => {
  it('returns the awaited seller reply over the async path', async () => {
    const { app } = server({
      phrased: (scripted, price) =>
        Promise.resolve(
          price === null ? scripted : `¡Hola! El precio es de €4.32 por unidad, pedido mínimo 1000.`
        ),
    })

    const opened = await app.inject({
      method: 'POST',
      url: '/mock-c/api/threads',
      payload: { item_id: 'c-gloves-01' },
    })
    expect(opened.statusCode).toBe(201)
    const { thread_id: threadId } = opened.json<{ thread_id: string }>()

    const sent = await app.inject({
      method: 'POST',
      url: `/mock-c/api/threads/${threadId}/messages`,
      payload: { body: BUYER_LINE },
    })
    expect(sent.statusCode).toBe(201)
    const body = sent.json<{ sent: { body: string }; received: Array<{ body: string }> }>()
    expect(body.sent.body).toBe(BUYER_LINE)
    expect(body.received.map((m) => m.body)).toEqual([
      '¡Hola! El precio es de €4.32 por unidad, pedido mínimo 1000.',
    ])

    const read = await app.inject({
      method: 'GET',
      url: `/mock-c/api/threads/${threadId}/messages`,
    })
    expect(read.json<{ messages: Array<{ body: string }> }>().messages.map((m) => m.body)).toEqual([
      BUYER_LINE,
      '¡Hola! El precio es de €4.32 por unidad, pedido mínimo 1000.',
    ])
    await app.close()
  })

  it('falls back to the scripted reply when the phraser drifts the price', async () => {
    const { app } = server({ phrased: () => Promise.resolve('EUR 1.00 per unit!') })

    const opened = await app.inject({
      method: 'POST',
      url: '/mock-c/api/threads',
      payload: { item_id: 'c-gloves-01' },
    })
    const { thread_id: threadId } = opened.json<{ thread_id: string }>()
    const sent = await app.inject({
      method: 'POST',
      url: `/mock-c/api/threads/${threadId}/messages`,
      payload: { body: BUYER_LINE },
    })
    expect(sent.json<{ received: Array<{ body: string }> }>().received.map((m) => m.body)).toEqual([
      SCRIPTED_FIRST,
    ])
    await app.close()
  })
})
