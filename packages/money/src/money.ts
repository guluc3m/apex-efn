import type { Currency } from '@apex/shared-types/currency'
import { CURRENCY_MINOR_UNITS } from '@apex/shared-types/currency'

export interface MoneyInput {
  amountMinor: number
  currency: Currency
}

export type MoneyErrorCode =
  | 'invalid_amount'
  | 'amount_out_of_range'
  | 'invalid_decimal'
  | 'invalid_ratios'
  | 'invalid_divisor'
  | 'division_by_zero'
  | 'currency_mismatch'
  | 'unsupported_currency'

/** Error with a stable code shared with `apex.domain.money` (ADR-300, ADR-301 rule 6). */
export class MoneyError extends Error {
  constructor(
    readonly code: MoneyErrorCode,
    message: string
  ) {
    super(message)
    this.name = 'MoneyError'
  }
}

const DECIMAL = /^(-?)(\d+)(?:\.(\d+))?$/
const MAX = BigInt(Number.MAX_SAFE_INTEGER)

const abs = (x: bigint): bigint => (x < 0n ? -x : x)

/** n / d rounded half away from zero (ADR-900 Q1). `d` is never 0. */
export function divideHalfAwayFromZero(n: bigint, d: bigint): bigint {
  const q = abs(n) / abs(d)
  const rounded = 2n * (abs(n) % abs(d)) >= abs(d) ? q + 1n : q
  return n < 0n !== d < 0n ? -rounded : rounded
}

/** A decimal string as an exact fraction `num / den`. */
function parseDecimal(value: unknown): { num: bigint; den: bigint } {
  const match = typeof value === 'string' ? DECIMAL.exec(value) : null
  if (!match)
    throw new MoneyError('invalid_decimal', `Not a plain decimal string: ${String(value)}`)
  const [, sign, whole, fraction = ''] = match
  const num = BigInt(whole! + fraction)
  return { num: sign ? -num : num, den: 10n ** BigInt(fraction.length) }
}

function minorUnits(currency: Currency): bigint {
  const units = (CURRENCY_MINOR_UNITS as Record<string, number | undefined>)[currency]
  if (units === undefined) {
    throw new MoneyError('unsupported_currency', `Unsupported currency: ${String(currency)}`)
  }
  return BigInt(units)
}

function checked(amount: bigint): bigint {
  if (abs(amount) > MAX) {
    throw new MoneyError('amount_out_of_range', `Amount outside ±(2^53 - 1): ${amount}`)
  }
  return amount
}

/**
 * Immutable money in integer minor units (ADR-301). No float ever enters or leaves: parse decimal strings,
 * print with `toDecimalString()`. Every fractional result rounds half away from zero.
 */
export class Money {
  readonly amountMinor: number
  readonly currency: Currency

  constructor(amountMinor: number, currency: Currency) {
    minorUnits(currency)
    if (!Number.isInteger(amountMinor)) {
      throw new MoneyError(
        'invalid_amount',
        `Amount must be integer minor units, got: ${String(amountMinor)}`
      )
    }
    if (!Number.isSafeInteger(amountMinor)) {
      throw new MoneyError('amount_out_of_range', `Amount outside ±(2^53 - 1): ${amountMinor}`)
    }
    this.amountMinor = amountMinor === 0 ? 0 : amountMinor
    this.currency = currency
  }

  static fromMinor(amountMinor: number, currency: Currency): Money {
    return new Money(amountMinor, currency)
  }

  /** "-12.345" in major units → minor units, rounded half away from zero. */
  static parse(amount: string, currency: Currency): Money {
    const { num, den } = parseDecimal(amount)
    return Money.of(divideHalfAwayFromZero(num * minorUnits(currency), den), currency)
  }

  static zero(currency: Currency): Money {
    return new Money(0, currency)
  }

  private static of(amount: bigint, currency: Currency): Money {
    return new Money(Number(checked(amount)), currency)
  }

  /** Exact major amount, e.g. "-12.34". */
  toDecimalString(): string {
    const units = minorUnits(this.currency)
    const digits = units.toString().length - 1
    const value = abs(BigInt(this.amountMinor))
    const fraction = (value % units).toString().padStart(digits, '0')
    return `${this.amountMinor < 0 ? '-' : ''}${value / units}${digits ? `.${fraction}` : ''}`
  }

  add(other: Money): Money {
    this.assertSameCurrency(other)
    return Money.of(BigInt(this.amountMinor) + BigInt(other.amountMinor), this.currency)
  }

  subtract(other: Money): Money {
    this.assertSameCurrency(other)
    return Money.of(BigInt(this.amountMinor) - BigInt(other.amountMinor), this.currency)
  }

  /** Multiply by an integer or a decimal string ("1.21") as an exact rational. */
  multiply(factor: number | string): Money {
    const { num, den } =
      typeof factor === 'number' && Number.isSafeInteger(factor)
        ? { num: BigInt(factor), den: 1n }
        : parseDecimal(factor)
    return Money.of(divideHalfAwayFromZero(BigInt(this.amountMinor) * num, den), this.currency)
  }

  divide(divisor: number): Money {
    if (!Number.isSafeInteger(divisor)) {
      throw new MoneyError('invalid_divisor', `Divisor must be an integer, got: ${String(divisor)}`)
    }
    if (divisor === 0) throw new MoneyError('division_by_zero', 'Cannot divide by zero')
    return Money.of(
      divideHalfAwayFromZero(BigInt(this.amountMinor), BigInt(divisor)),
      this.currency
    )
  }

  /**
   * Split by non-negative integer ratios. Largest remainder on the absolute amount, ties to the lower
   * index, sign last. The parts always sum to this amount and a zero ratio always gets zero.
   */
  allocate(ratios: number[]): Money[] {
    if (ratios.length === 0 || !ratios.every((r) => Number.isSafeInteger(r) && r >= 0)) {
      throw new MoneyError(
        'invalid_ratios',
        `Ratios must be non-negative integers: ${String(ratios)}`
      )
    }
    const weights = ratios.map(BigInt)
    const total = weights.reduce((a, b) => a + b, 0n)
    if (total === 0n) throw new MoneyError('invalid_ratios', 'Ratios must have a positive sum')

    const amount = abs(BigInt(this.amountMinor))
    const shares = weights.map((w) => (amount * w) / total)
    const left = amount - shares.reduce((a, b) => a + b, 0n)
    const byRemainder = weights
      .map((w, i) => ({ i, r: (amount * w) % total }))
      .sort((a, b) => (a.r === b.r ? a.i - b.i : a.r > b.r ? -1 : 1))
    // left is below the count of positive remainders, so a zero ratio never gets an extra unit
    for (const { i } of byRemainder.slice(0, Number(left))) shares[i]! += 1n
    const sign = this.amountMinor < 0 ? -1n : 1n
    return shares.map((s) => Money.of(sign * s, this.currency))
  }

  negate(): Money {
    return new Money(-this.amountMinor, this.currency)
  }

  abs(): Money {
    return new Money(Math.abs(this.amountMinor), this.currency)
  }

  isZero(): boolean {
    return this.amountMinor === 0
  }

  isPositive(): boolean {
    return this.amountMinor > 0
  }

  isNegative(): boolean {
    return this.amountMinor < 0
  }

  equals(other: Money): boolean {
    return this.amountMinor === other.amountMinor && this.currency === other.currency
  }

  compareTo(other: Money): number {
    this.assertSameCurrency(other)
    return Math.sign(this.amountMinor - other.amountMinor)
  }

  greaterThan(other: Money): boolean {
    return this.compareTo(other) > 0
  }

  lessThan(other: Money): boolean {
    return this.compareTo(other) < 0
  }

  greaterThanOrEqual(other: Money): boolean {
    return this.compareTo(other) >= 0
  }

  lessThanOrEqual(other: Money): boolean {
    return this.compareTo(other) <= 0
  }

  /** Display only. Formats the exact decimal string (Intl.NumberFormat v3), never a float. */
  format(locale = 'en-US'): string {
    // The configured TS lib types format() without the ES2023 string overload
    const exact = this.toDecimalString() as unknown as number
    return new Intl.NumberFormat(locale, { style: 'currency', currency: this.currency }).format(
      exact
    )
  }

  toJSON(): MoneyInput {
    return { amountMinor: this.amountMinor, currency: this.currency }
  }

  private assertSameCurrency(other: Money): void {
    if (this.currency !== other.currency) {
      throw new MoneyError(
        'currency_mismatch',
        `Currency mismatch: ${this.currency} vs ${other.currency}`
      )
    }
  }
}
