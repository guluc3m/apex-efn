/** Formatting and parsing helpers. Every currency the mock serves has two minor digits. */

export function formatMinor(minor: number): string {
  const sign = minor < 0 ? '-' : ''
  const abs = Math.abs(minor)
  const major = Math.floor(abs / 100)
  const cents = abs % 100
  return `${sign}${major}.${cents.toString().padStart(2, '0')}`
}

const SYMBOLS: Readonly<Record<string, string>> = {
  '€': 'EUR',
  $: 'USD',
  '¥': 'CNY',
  '£': 'GBP',
  元: 'CNY',
}
const CODE = String.raw`EUR|USD|CNY|RMB|GBP|€|\$|¥|£|元`
const AMOUNT = String.raw`\d+(?:[.,]\d{1,2})?`
const PRICE_RE = new RegExp(
  String.raw`(?:(${CODE})\s*(${AMOUNT}))|(?:(${AMOUNT})\s*(${CODE}))`,
  'gi'
)

export interface ParsedPrice {
  minor: number
  currency: string | null
}

function toMinor(amount: string): number {
  const [major = '0', frac = ''] = amount.replace(',', '.').split('.')
  return Number.parseInt(major, 10) * 100 + Number.parseInt(frac.padEnd(2, '0') || '0', 10)
}

function normaliseCode(code: string): string {
  const upper = code.toUpperCase()
  if (upper === 'RMB') return 'CNY'
  return SYMBOLS[code] ?? upper
}

/**
 * Every price in a chat message, in order of appearance. Only amounts next to a currency code or symbol
 * count, so quantities such as "5000 units" are never mistaken for a price.
 */
export function parsePrices(text: string): ParsedPrice[] {
  const found: ParsedPrice[] = []
  for (const m of text.matchAll(PRICE_RE)) {
    const code = m[1] ?? m[4]
    const amount = m[2] ?? m[3]
    if (!code || !amount) continue
    found.push({ minor: toMinor(amount), currency: normaliseCode(code) })
  }
  return found
}

/** The last price in a chat message, or null when it states none. */
export function parseLastPrice(text: string): ParsedPrice | null {
  const found = parsePrices(text)
  return found.length === 0 ? null : (found[found.length - 1] ?? null)
}
