/**
 * Tiny helpers over `node-html-parser` for the `mock-b` adapter.
 *
 * Every read that can fail names the `data-testid` it wanted and nothing else: a page that changed shape answers
 * `dom_changed` (the runbook in docs/runbooks/dom-change.md) without echoing page content, which may contain a
 * seller's data or a price.
 */

import { parse, type HTMLElement } from 'node-html-parser'

import { WorkerError } from '../../errors.js'

export type Html = HTMLElement

export function parseHtml(body: string): Html {
  return parse(body)
}

export function domChanged(what: string): WorkerError {
  return new WorkerError('dom_changed', 502, { detail: `mock-b page changed: missing ${what}` })
}

export function byTestId(root: Html, testId: string): Html | null {
  return root.querySelector(`[data-testid="${testId}"]`)
}

export function allByTestId(root: Html, testId: string): Html[] {
  return root.querySelectorAll(`[data-testid="${testId}"]`)
}

export function requireByTestId(root: Html, testId: string): Html {
  const element = byTestId(root, testId)
  if (element === null) {
    throw domChanged(testId)
  }
  return element
}

export function attr(element: Html, name: string): string | null {
  const value = element.getAttribute(name)
  return value === undefined ? null : value
}

export function requireAttr(element: Html, name: string, testId: string): string {
  const value = attr(element, name)
  if (value === null || value === '') {
    throw domChanged(`${name} on ${testId}`)
  }
  return value
}

export function text(element: Html): string {
  return element.textContent.trim()
}

/** Integer `data-*` attribute. A missing or non-numeric value is a page change, never a zero. */
export function intAttr(element: Html, name: string, testId: string): number {
  const raw = requireAttr(element, name, testId)
  const value = Number(raw)
  if (!Number.isInteger(value)) {
    throw domChanged(`numeric ${name} on ${testId}`)
  }
  return value
}

export function optionalIntAttr(element: Html, name: string): number | null {
  const raw = attr(element, name)
  if (raw === null || raw === '') {
    return null
  }
  const value = Number(raw)
  return Number.isInteger(value) ? value : null
}

/** A price read from a page: integer minor units and the currency code as the page states it. */
export interface Price {
  minor: number
  currency: string
}

/**
 * Currency codes that are *not* the four the contract supports. Seeing one is enough to refuse the price:
 * reading `CAD $12.99` as USD would be worse than reporting no price at all.
 */
const OTHER_CURRENCY_CODES = new Set([
  'AED',
  'ARS',
  'AUD',
  'BGN',
  'BRL',
  'CAD',
  'CHF',
  'CLP',
  'COP',
  'CZK',
  'DKK',
  'EGP',
  'HKD',
  'HUF',
  'IDR',
  'ILS',
  'INR',
  'ISK',
  'JPY',
  'KRW',
  'MAD',
  'MXN',
  'MYR',
  'NGN',
  'NOK',
  'NZD',
  'PEN',
  'PHP',
  'PKR',
  'PLN',
  'RON',
  'RUB',
  'SAR',
  'SEK',
  'SGD',
  'THB',
  'TRY',
  'TWD',
  'UAH',
  'VND',
  'ZAR',
])

/** `A$`, `C$`, `HK$`... are not USD even though they contain a dollar sign. */
const NON_US_DOLLAR_PREFIXES = new Set([
  'A',
  'AU',
  'BR',
  'C',
  'CA',
  'CL',
  'CO',
  'HK',
  'MX',
  'NT',
  'NZ',
  'R',
  'S',
  'SG',
  'TW',
])

/**
 * Reads the currency the text states, or `null` when it says nothing, says several different things or names a
 * currency we do not support. `¥` is deliberately not mapped: it is JPY on some pages and CNY on others.
 */
function currencyOf(value: string): string | null {
  const found = new Set<string>()

  for (const match of value.matchAll(/(?<![A-Za-z])(GBP|USD|EUR|CNY)(?![A-Za-z])/gi)) {
    const code = match[1]
    if (code !== undefined) {
      found.add(code.toUpperCase())
    }
  }

  for (const match of value.matchAll(/(?<![A-Za-z])([A-Z]{3})(?![A-Za-z])/g)) {
    const code = match[1]
    if (code !== undefined && OTHER_CURRENCY_CODES.has(code)) {
      return null
    }
  }

  for (let index = value.indexOf('$'); index !== -1; index = value.indexOf('$', index + 1)) {
    const adjacent = /([A-Za-z]{1,3})$/.exec(value.slice(0, index))?.[1]?.toUpperCase() ?? ''
    if (adjacent === 'US' || adjacent === 'USD') {
      found.add('USD')
    } else if (NON_US_DOLLAR_PREFIXES.has(adjacent) || OTHER_CURRENCY_CODES.has(adjacent)) {
      return null
    } else {
      found.add('USD')
    }
  }

  if (value.includes('£')) {
    found.add('GBP')
  }
  if (value.includes('€')) {
    found.add('EUR')
  }

  if (found.size !== 1) {
    return null
  }
  const currencies = [...found]
  return currencies[0] ?? null
}

/**
 * One numeric token -> integer minor units. The decimal separator is the rightmost `.` or `,` followed by exactly
 * two digits; the other separator, when present, must group the integer part in threes. Anything else is refused:
 * `£51`, `£51.7`, `1.299` and `1,29.00` are all ambiguous.
 */
function amountOf(token: string): number | null {
  const decimalIndex = Math.max(token.lastIndexOf(','), token.lastIndexOf('.'))
  if (decimalIndex < 0) {
    return null
  }
  const decimalSeparator = token[decimalIndex]
  if (decimalSeparator === undefined) {
    return null
  }
  const fraction = token.slice(decimalIndex + 1)
  if (!/^\d{2}$/.test(fraction)) {
    return null
  }
  const integerPart = token.slice(0, decimalIndex)
  if (integerPart === '' || integerPart.includes(decimalSeparator)) {
    return null
  }

  const thousandsSeparator = decimalSeparator === ',' ? '.' : ','
  const groups = integerPart.split(thousandsSeparator)
  const first = groups[0]
  if (first === undefined || !/^\d+$/.test(first)) {
    return null
  }
  if (groups.length > 1) {
    if (!/^\d{1,3}$/.test(first)) {
      return null
    }
    for (const group of groups.slice(1)) {
      if (!/^\d{3}$/.test(group)) {
        return null
      }
    }
  }

  const minor = Number(groups.join('')) * 100 + Number(fraction)
  return Number.isSafeInteger(minor) ? minor : null
}

/**
 * Conservative fallback for pages that render a price as text instead of `data-minor`/`data-currency`.
 *
 * It accepts exactly one unambiguous amount with one unambiguous currency. No decimal part, more than one number,
 * a percentage, a negative amount, a conflicting currency or a currency we do not support all return `null`; the
 * caller decides whether that is a skipped listing or a page change. `¥` and space/apostrophe thousands separators
 * are deliberately unsupported.
 */
export function parsePriceText(raw: string): Price | null {
  const value = raw.replace(/\s+/g, ' ').trim()
  if (value === '' || value.includes('%') || /\bpercent\b/i.test(value)) {
    return null
  }
  if (/(?:^|[\s(£€$])[-−]\s*[£€$]?\s*\d/.test(value) || /[-−]\s*$/.test(value)) {
    return null
  }

  const currency = currencyOf(value)
  if (currency === null) {
    return null
  }

  const tokens = value.match(/\d+(?:[.,]\d+)*/g) ?? []
  if (tokens.length !== 1) {
    return null
  }
  const token = tokens[0]
  if (token === undefined) {
    return null
  }
  const tokenIndex = value.indexOf(token)
  const beforeToken = tokenIndex > 0 ? value[tokenIndex - 1] : undefined
  if (beforeToken === '.' || beforeToken === ',') {
    return null
  }

  const minor = amountOf(token)
  return minor === null ? null : { minor, currency }
}

/**
 * `data-minor` + `data-currency` on a price element, with `parsePriceText` as a fallback when the attributes are
 * absent or invalid. A valid `data-minor` still requires `data-currency`, exactly as before: the attribute path
 * never guesses a currency.
 */
export function priceOf(element: Html, testId: string): Price | null {
  const rawMinor = attr(element, 'data-minor')
  if (rawMinor !== null && rawMinor !== '') {
    const minor = Number(rawMinor)
    if (Number.isInteger(minor)) {
      return { minor, currency: requireAttr(element, 'data-currency', testId) }
    }
  }
  return parsePriceText(text(element))
}

/** "30%" -> 0.3. Anything else is a page change. */
export function ratioOf(element: Html, testId: string): number | null {
  const raw = attr(element, 'data-value')
  if (raw === null || raw === '') {
    return null
  }
  const match = /^(\d+(?:\.\d+)?)%$/.exec(raw)
  if (match?.[1] === undefined) {
    throw domChanged(`percentage on ${testId}`)
  }
  return Number(match[1]) / 100
}

/** "yes" | "no" -> boolean; anything else is `null` (the platform did not say). */
export function booleanOf(element: Html): boolean | null {
  const raw = attr(element, 'data-value')
  if (raw === 'yes') {
    return true
  }
  if (raw === 'no') {
    return false
  }
  return null
}

export function numberValue(element: Html): number | null {
  const raw = attr(element, 'data-value')
  if (raw === null || raw === '') {
    return null
  }
  const value = Number(raw)
  return Number.isFinite(value) ? value : null
}
