import type { Currency } from '@apex/shared-types/contracts/browser-worker'

import { WorkerError } from '../errors.js'

const PLAIN = /^(\d+)(?:([.,])(\d{1,2}))?$/
const GROUPED =
  /^(\d{1,3})((?:[ \u00a0\u202f]\d{3})+|(?:,\d{3})+|(?:\.\d{3})+)(?:([.,])(\d{1,2}))?$/
const MINOR_PER_MAJOR = BigInt(100)
const MAX_SAFE = BigInt(Number.MAX_SAFE_INTEGER)

function rejected(): never {
  throw new WorkerError('dom_changed', 502, {
    retryable: false,
    detail: 'price text is not a decimal amount with at most 2 decimals',
  })
}

function toMinor(whole: string, decimals: string | undefined): number {
  const fraction = decimals === undefined ? BigInt(0) : BigInt(decimals.padEnd(2, '0'))
  const minor = BigInt(whole) * MINOR_PER_MAJOR + fraction
  if (minor > MAX_SAFE) {
    rejected()
  }
  return Number(minor)
}

/**
 * Parses a price as shown on a platform into integer minor units, without floats.
 *
 * Accepts `4.45`, `4,45`, `12`, `0.5`, `1234567.89`, thousands groups with a space (`1 234.50`) and with `,` or `.`
 * when the decimal separator is the other one (`1,234.50`, `1.234,50`), or repeated groups (`1,234,567`).
 * A single `,`/`.` followed by three digits is ambiguous (`1.005`, `1,234`) and is rejected, never guessed.
 * Negative values and more than two decimals are rejected too.
 */
export function parseDecimalMinor(value: string): number {
  const text = value.trim()
  const plain = PLAIN.exec(text)
  if (plain !== null) {
    return toMinor(plain[1] ?? '', plain[3])
  }
  const grouped = GROUPED.exec(text)
  if (grouped === null) {
    rejected()
  }
  const [, head = '', groups = '', decimalSeparator, decimals] = grouped
  const groupSeparator = groups.charAt(0)
  const groupCount = (groups.match(/\d{3}/g) ?? []).length
  if (decimalSeparator !== undefined && decimalSeparator === groupSeparator) {
    rejected()
  }
  if (
    (groupSeparator === ',' || groupSeparator === '.') &&
    groupCount === 1 &&
    decimalSeparator === undefined
  ) {
    rejected()
  }
  const whole = head + groups.replace(/\D/g, '')
  return toMinor(whole, decimals)
}

/** Maps a platform currency label to the closed contract enum. Unknown labels return null, never a guess. */
export function toContractCurrency(code: string): Currency | null {
  const upper = code.trim().toUpperCase()
  if (upper === 'RMB') {
    return 'CNY'
  }
  if (upper === 'EUR' || upper === 'USD' || upper === 'CNY') {
    return upper
  }
  return null
}
