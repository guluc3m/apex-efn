import { afterAll, describe, expect, it } from 'vitest'

import { PERSONA_IDS, type PersonaId } from '../fixtures/schema.js'
import { testServer } from '../test-helpers.js'

import { parseIntent } from './personas.js'

const SCRIPT = [
  'Hello, we are a distributor in Spain and need 5000 units per month, recurring. What volume tiers do you offer?',
  'Thanks. With 5000 units and a recurring order, could you do EUR 3.90 per unit?',
  'Could you meet us at EUR 4.30?',
  'Please confirm the final price in writing, and quote it in EUR.',
]

/** Opens a chat on a seller whose product is in EUR, forces a persona, plays the script. */
function play(persona: PersonaId, seed = 7) {
  const { app, chats } = testServer(seed)
  void app.close()
  const chat = chats.open('mock-b', 'b-standard-coop', 'b-gloves-03')
  chats.setChatPersona(chat.id, persona)
  for (const line of SCRIPT) void chats.send(chat.id, line)
  return chats.snapshot(chat.id)
}

describe('buyer intent parsing', () => {
  it('extracts offers, tiers, quantities and currency requests', () => {
    expect(parseIntent('need 5000 units, what volume tiers?')).toMatchObject({
      quantity: 5000,
      wantsTiers: true,
      offer: null,
    })
    expect(parseIntent('could you do EUR 3.90?').offer).toEqual({ minor: 390, currency: 'EUR' })
    expect(parseIntent('please quote in EUR').requestedCurrency).toBe('EUR')
  })
})

describe('personas', () => {
  it.each(PERSONA_IDS)('%s is deterministic for a given seed', (persona) => {
    expect(play(persona)).toEqual(play(persona))
  })

  it('cooperative: gives tiers, concedes down to its floor and agrees in writing', () => {
    const s = play('cooperative')
    expect(s.messages[1]?.text).toMatch(/tiers/i)
    expect(s.agreed).not.toBeNull()
    expect(s.agreed?.minor).toBeGreaterThanOrEqual(s.floor.minor)
    expect(s.messages.at(-1)?.text).toMatch(/Confirmed in writing/)
    expect(s.flags).toEqual([])
  })

  it('never agrees below its floor, whatever the buyer offers', () => {
    const { app, chats } = testServer()
    void app.close()
    const chat = chats.open('mock-b', 'b-standard-coop', 'b-gloves-03')
    chats.setChatPersona(chat.id, 'cooperative')
    for (const p of ['1.00', '2.00', '3.00', '3.50']) void chats.send(chat.id, `EUR ${p}`)
    const s = chats.snapshot(chat.id)
    expect(s.agreed).toBeNull()
    expect(s.lastQuote?.minor).toBeGreaterThanOrEqual(s.floor.minor)
  })

  it('aggressive: adds closing pressure from round 2', () => {
    const s = play('aggressive')
    expect(s.flags).toContain('closing_pressure')
    expect(s.messages.some((m) => m.role === 'seller' && /close TODAY/.test(m.text))).toBe(true)
  })

  it('evasive: never states a price', () => {
    const s = play('evasive')
    expect(s.lastQuote).toBeNull()
    expect(s.flags).toContain('no_price_given')
  })

  it('off_platform: asks to move the deal off the platform', () => {
    const s = play('off_platform')
    expect(s.flags).toContain('off_platform_request')
    expect(
      s.messages.some((m) => m.role === 'seller' && /WhatsApp|bank transfer/i.test(m.text))
    ).toBe(true)
  })

  it('sensitive_data: asks for tax id and bank details', () => {
    const s = play('sensitive_data')
    expect(s.flags).toContain('sensitive_data_request')
    expect(s.messages.some((m) => m.role === 'seller' && /tax ID|bank/i.test(m.text))).toBe(true)
  })

  it('lowball: quotes an anomalously low price', () => {
    const s = play('lowball')
    expect(s.flags).toContain('anomalous_price')
    expect(s.lastQuote?.minor).toBeLessThan(465 * 0.5)
  })

  it('chinese: replies in Chinese', () => {
    const s = play('chinese')
    expect(
      s.messages.filter((m) => m.role === 'seller').every((m) => /[\u4e00-\u9fff]/.test(m.text))
    ).toBe(true)
  })

  it('truncated: cuts replies short', () => {
    const s = play('truncated')
    expect(s.flags).toContain('truncated')
    const cooperative = play('cooperative')
    const t = s.messages.filter((m) => m.role === 'seller').map((m) => m.text.length)
    const c = cooperative.messages.filter((m) => m.role === 'seller').map((m) => m.text.length)
    expect(t.every((len, i) => len < (c[i] ?? 0))).toBe(true)
  })

  it('unsupported_currency: quotes in GBP until asked for a supported currency', () => {
    const { app, chats } = testServer()
    void app.close()
    const chat = chats.open('mock-b', 'b-standard-coop', 'b-gloves-03')
    chats.setChatPersona(chat.id, 'unsupported_currency')
    void chats.send(chat.id, 'Hello, price for 1000 units?')
    expect(chats.snapshot(chat.id).lastQuote?.currency).toBe('GBP')
    expect(chats.snapshot(chat.id).flags).toContain('unsupported_currency')
    void chats.send(chat.id, 'Could you please quote in EUR?')
    expect(chats.snapshot(chat.id).lastQuote?.currency).toBe('EUR')
  })
})

describe('control surface', () => {
  const { app } = testServer()
  afterAll(() => app.close())

  it('sets a persona per seller, exposes ground truth and resets with a seed', async () => {
    const set = await app.inject({
      method: 'PUT',
      url: '/__control/sellers/a-solid-veteran/persona',
      payload: { persona: 'lowball' },
    })
    expect(set.statusCode).toBe(200)
    const open = await app.inject({
      method: 'POST',
      url: '/mock-a/api/conversations',
      payload: { vendor_id: 'a-solid-veteran', listing_id: 'a-gloves-01' },
    })
    const id = open.json<{ conversation_id: string }>().conversation_id
    await app.inject({
      method: 'POST',
      url: `/mock-a/api/conversations/${id}/messages`,
      payload: { body: 'Hi, price?' },
    })
    const snap = await app.inject({ method: 'GET', url: `/__control/chats/${id}` })
    expect(snap.json()).toMatchObject({ persona: 'lowball', flags: ['anomalous_price'], round: 1 })

    const reset = await app.inject({
      method: 'POST',
      url: '/__control/reset',
      payload: { seed: 99 },
    })
    expect(reset.json()).toEqual({ ok: true, seed: 99 })
    expect((await app.inject({ method: 'GET', url: '/__control/chats' })).json()).toEqual({
      chats: [],
    })
  })

  it('rejects unknown personas', async () => {
    const res = await app.inject({
      method: 'PUT',
      url: '/__control/sellers/a-solid-veteran/persona',
      payload: { persona: 'pirate' },
    })
    expect(res.statusCode).toBe(400)
  })
})
