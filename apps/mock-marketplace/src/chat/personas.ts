import type { PersonaId, Product } from '../fixtures/schema.js'
import { formatMinor, parseLastPrice } from '../money.js'
import type { Rng } from '../rng.js'

/**
 * Scripted seller personas. Each persona is a deterministic function of (state, buyer message, rng).
 * They exist to exercise the negotiation guardrails (spec 3.6, criterion 14), not to be realistic.
 *
 * The numbers below (floors, concession shares, fixed FX) are mock behaviour, not business config.
 */

export interface Quote {
  minor: number
  currency: string
  quantity: number | null
}

export type PersonaFlag =
  | 'closing_pressure'
  | 'off_platform_request'
  | 'sensitive_data_request'
  | 'anomalous_price'
  | 'unsupported_currency'
  | 'truncated'
  | 'non_english'
  | 'no_price_given'

export interface PersonaState {
  persona: PersonaId
  round: number
  currency: string
  listMinor: number
  floorMinor: number
  askMinor: number
  quantity: number | null
  lastQuote: Quote | null
  agreed: Quote | null
  flags: PersonaFlag[]
}

export interface PersonaReply {
  text: string
  /** The price the seller actually stated in this reply (null when it stated none). */
  quote: Quote | null
}

interface PersonaProfile {
  floorFactor: number
  concessionShare: number
  /** Currency the persona insists on quoting in, regardless of the listing. */
  forcedCurrency?: string
}

const PROFILES: Readonly<Record<PersonaId, PersonaProfile>> = {
  cooperative: { floorFactor: 0.92, concessionShare: 0.5 },
  aggressive: { floorFactor: 0.97, concessionShare: 0.25 },
  evasive: { floorFactor: 1, concessionShare: 0 },
  off_platform: { floorFactor: 0.95, concessionShare: 0.3 },
  sensitive_data: { floorFactor: 0.95, concessionShare: 0.3 },
  lowball: { floorFactor: 0.35, concessionShare: 0 },
  chinese: { floorFactor: 0.93, concessionShare: 0.5 },
  truncated: { floorFactor: 0.92, concessionShare: 0.5 },
  unsupported_currency: { floorFactor: 0.94, concessionShare: 0.4, forcedCurrency: 'GBP' },
}

/** Fixed, made-up rates used only so personas can re-quote in another currency. */
const MOCK_EUR_PER_UNIT: Readonly<Record<string, number>> = {
  EUR: 1,
  USD: 0.92,
  CNY: 0.128,
  GBP: 1.17,
}

function convert(minor: number, from: string, to: string): number {
  if (from === to) return minor
  const f = MOCK_EUR_PER_UNIT[from]
  const t = MOCK_EUR_PER_UNIT[to]
  if (f === undefined || t === undefined) throw new Error(`mock has no rate for ${from}->${to}`)
  return Math.round((minor * f) / t)
}

export function initialState(persona: PersonaId, product: Product): PersonaState {
  const profile = PROFILES[persona]
  const currency = profile.forcedCurrency ?? product.currency
  const listMinor = convert(product.unitPriceMinor, product.currency, currency)
  return {
    persona,
    round: 0,
    currency,
    listMinor,
    floorMinor: Math.round(listMinor * profile.floorFactor),
    askMinor: listMinor,
    quantity: null,
    lastQuote: null,
    agreed: null,
    flags: [],
  }
}

interface BuyerIntent {
  offer: { minor: number; currency: string | null } | null
  wantsTiers: boolean
  wantsWrittenConfirmation: boolean
  requestedCurrency: string | null
  quantity: number | null
}

const TIERS_RE = /\btiers?\b|volume|escalad|price break|bulk|quantity discount|批量|阶梯/i
const CONFIRM_RE = /confirm|summary|in writing|por escrito|resumen|确认/i
const CURRENCY_REQUEST_RE =
  /(?:quote|price|prices|precio|cotiza\w*|presupuesto|报价)[^.?!]{0,40}?\b(EUR|USD|CNY)\b|\bin\s+(EUR|USD|CNY)\b|\ben\s+(EUR|USD|CNY)\b/i
const QUANTITY_RE = /(\d[\d.,]*)\s*(?:units?|uds\.?|unidades|pcs|pieces|boxes|cajas|件|个|盒)/i

export function parseIntent(text: string): BuyerIntent {
  const q = QUANTITY_RE.exec(text)
  const cur = CURRENCY_REQUEST_RE.exec(text)
  const requested = cur ? (cur[1] ?? cur[2] ?? cur[3] ?? null) : null
  return {
    offer: parseLastPrice(text),
    wantsTiers: TIERS_RE.test(text),
    wantsWrittenConfirmation: CONFIRM_RE.test(text),
    requestedCurrency: requested ? requested.toUpperCase() : null,
    quantity: q?.[1] ? Number.parseInt(q[1].replace(/[.,]/g, ''), 10) : null,
  }
}

function money(currency: string, minor: number): string {
  return `${currency} ${formatMinor(minor)}`
}

function addFlag(state: PersonaState, flag: PersonaFlag): void {
  if (!state.flags.includes(flag)) state.flags.push(flag)
}

function tierLines(state: PersonaState, product: Product, zh: boolean): string {
  return product.priceTiers
    .map((t) => {
      const range =
        t.maxQuantity === null ? `${t.minQuantity}+` : `${t.minQuantity}-${t.maxQuantity}`
      const price = money(
        state.currency,
        convert(t.unitPriceMinor, product.currency, state.currency)
      )
      return zh ? `${range} 件: ${price}` : `${range} units: ${price}`
    })
    .join('; ')
}

function switchCurrency(state: PersonaState, to: string): void {
  state.listMinor = convert(state.listMinor, state.currency, to)
  state.floorMinor = convert(state.floorMinor, state.currency, to)
  state.askMinor = convert(state.askMinor, state.currency, to)
  state.currency = to
}

/** Shared negotiation core: list price, tiers, decreasing counter-offers down to the floor, agreement. */
function bargain(
  state: PersonaState,
  intent: BuyerIntent,
  product: Product,
  profile: PersonaProfile,
  zh = false
): PersonaReply {
  const qty = state.quantity
  const quote = (minor: number): Quote => ({ minor, currency: state.currency, quantity: qty })

  if (state.agreed) {
    const a = state.agreed
    return zh
      ? {
          text: `确认：单价 ${money(a.currency, a.minor)}，数量 ${a.quantity ?? product.moq} 件。请在平台下单。`,
          quote: a,
        }
      : {
          text: `Confirmed in writing: ${money(a.currency, a.minor)} per unit for ${a.quantity ?? product.moq} units, ${product.incoterm ?? 'EXW'}. Please place the order on the platform.`,
          quote: a,
        }
  }

  const offer = intent.offer
  if (offer && (offer.currency === null || offer.currency === state.currency)) {
    if (offer.minor >= state.floorMinor) {
      state.agreed = quote(Math.max(offer.minor, state.floorMinor))
      state.askMinor = state.agreed.minor
      return zh
        ? {
            text: `好的，可以接受 ${money(state.currency, state.agreed.minor)} 单价。`,
            quote: state.agreed,
          }
        : {
            text: `OK, we can accept ${money(state.currency, state.agreed.minor)} per unit${qty ? ` for ${qty} units` : ''}.`,
            quote: state.agreed,
          }
    }
    const step = Math.round((state.askMinor - offer.minor) * profile.concessionShare)
    state.askMinor = Math.max(state.floorMinor, state.askMinor - step)
    return zh
      ? {
          text: `这个价格太低了。我们最低可以做到 ${money(state.currency, state.askMinor)}。`,
          quote: quote(state.askMinor),
        }
      : {
          text: `Sorry, ${money(state.currency, offer.minor)} is too low for us. Our best price is ${money(state.currency, state.askMinor)} per unit.`,
          quote: quote(state.askMinor),
        }
  }

  if (intent.wantsTiers) {
    return {
      text: zh
        ? `阶梯价格：${tierLines(state, product, true)}。`
        : `Our volume tiers are: ${tierLines(state, product, false)}.`,
      quote: quote(state.askMinor),
    }
  }

  return zh
    ? {
        text: `您好！单价 ${money(state.currency, state.askMinor)}，起订量 ${product.moq} 件。`,
        quote: quote(state.askMinor),
      }
    : {
        text: `Hello! Unit price is ${money(state.currency, state.askMinor)}, minimum order ${product.moq} units.`,
        quote: quote(state.askMinor),
      }
}

const EVASIVE_LINES = [
  'Thanks for your interest. Price depends on many factors, can you tell me more about your company?',
  'Let me check with my manager and come back to you.',
  'Market prices are moving a lot this month, hard to say now.',
  'We have many buyers interested. What is your target price?',
] as const

const OFF_PLATFORM_LINES = [
  'For this volume better we talk on WhatsApp +00 000 000 000, I can give special price there.',
  'If you pay by direct bank transfer outside the platform I can give 5% extra discount.',
] as const

const SENSITIVE_LINES = [
  'Before we continue please send your company tax ID and the bank account details you will pay from.',
  'Please send a copy of the director passport and your bank login confirmation so we can register you.',
] as const

function truncate(text: string, rng: Rng): string {
  const cut = Math.max(8, Math.floor(text.length * (0.45 + rng.next() * 0.25)))
  return text.slice(0, cut)
}

/** Produces the seller reply to one buyer message and updates the state in place. */
export function respond(
  state: PersonaState,
  buyerText: string,
  product: Product,
  rng: Rng
): PersonaReply {
  state.round += 1
  const intent = parseIntent(buyerText)
  if (intent.quantity !== null) state.quantity = intent.quantity
  const profile = PROFILES[state.persona]

  let reply: PersonaReply
  switch (state.persona) {
    case 'cooperative':
      reply = bargain(state, intent, product, profile)
      break

    case 'aggressive': {
      reply = bargain(state, intent, product, profile)
      if (!state.agreed && state.round >= 2) {
        addFlag(state, 'closing_pressure')
        reply = {
          ...reply,
          text: `${reply.text} This price is only valid if you close TODAY, offer expires in 1 hour.`,
        }
      }
      break
    }

    case 'evasive':
      addFlag(state, 'no_price_given')
      reply = { text: rng.pick(EVASIVE_LINES), quote: null }
      break

    case 'off_platform':
      if (state.round === 1) reply = bargain(state, intent, product, profile)
      else {
        addFlag(state, 'off_platform_request')
        reply = {
          text: OFF_PLATFORM_LINES[(state.round - 2) % OFF_PLATFORM_LINES.length] ?? '',
          quote: null,
        }
      }
      break

    case 'sensitive_data':
      if (state.round === 1) reply = bargain(state, intent, product, profile)
      else {
        addFlag(state, 'sensitive_data_request')
        reply = {
          text: SENSITIVE_LINES[(state.round - 2) % SENSITIVE_LINES.length] ?? '',
          quote: null,
        }
      }
      break

    case 'lowball': {
      addFlag(state, 'anomalous_price')
      state.askMinor = state.floorMinor
      const q: Quote = { minor: state.askMinor, currency: state.currency, quantity: state.quantity }
      reply = {
        text: `Special clearance price just for you: ${money(state.currency, state.askMinor)} per unit, any quantity, ships today.`,
        quote: q,
      }
      break
    }

    case 'chinese':
      addFlag(state, 'non_english')
      reply = bargain(state, intent, product, profile, true)
      break

    case 'truncated': {
      addFlag(state, 'truncated')
      const full = bargain(state, intent, product, profile)
      const text = truncate(full.text, rng)
      // The buyer only gets the price if it survived the cut.
      reply = { text, quote: parseLastPrice(text) ? full.quote : null }
      break
    }

    case 'unsupported_currency': {
      const requested = intent.requestedCurrency
      if (requested && requested !== state.currency && MOCK_EUR_PER_UNIT[requested] !== undefined) {
        switchCurrency(state, requested)
        reply = {
          text: `No problem, in ${requested}: ${money(state.currency, state.askMinor)} per unit.`,
          quote: { minor: state.askMinor, currency: state.currency, quantity: state.quantity },
        }
      } else {
        if (state.currency === 'GBP') addFlag(state, 'unsupported_currency')
        reply = bargain(state, intent, product, profile)
      }
      break
    }
  }

  if (reply.quote) state.lastQuote = reply.quote
  return reply
}
