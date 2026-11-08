import type { Currency } from '@apex/shared-types/currency'
import { CURRENCY_MINOR_UNITS } from '@apex/shared-types/currency'

export interface MoneyInput {
  amountMinor: number
  currency: Currency
}

/**
 * Immutable money value object with integer arithmetic.
 * All operations maintain cent/fen precision without floating point errors.
 */
export class Money {
  readonly amountMinor: number
  readonly currency: Currency

  constructor(amountMinor: number, currency: Currency) {
    if (!Number.isInteger(amountMinor)) {
      throw new Error(`Amount must be an integer in minor units, got: ${amountMinor}`)
    }
    this.amountMinor = amountMinor
    this.currency = currency
  }

  static fromMinor(amountMinor: number, currency: Currency): Money {
    return new Money(amountMinor, currency)
  }

  static fromMajor(amountMajor: number, currency: Currency): Money {
    const multiplier = CURRENCY_MINOR_UNITS[currency]
    const amountMinor = Math.round(amountMajor * multiplier)
    return new Money(amountMinor, currency)
  }

  static zero(currency: Currency): Money {
    return new Money(0, currency)
  }

  toMajor(): number {
    return this.amountMinor / CURRENCY_MINOR_UNITS[this.currency]
  }

  add(other: Money): Money {
    this.assertSameCurrency(other)
    return new Money(this.amountMinor + other.amountMinor, this.currency)
  }

  subtract(other: Money): Money {
    this.assertSameCurrency(other)
    return new Money(this.amountMinor - other.amountMinor, this.currency)
  }

  multiply(factor: number): Money {
    const result = Math.round(this.amountMinor * factor)
    return new Money(result, this.currency)
  }

  divide(divisor: number): Money {
    if (divisor === 0) {
      throw new Error('Cannot divide by zero')
    }
    const result = Math.round(this.amountMinor / divisor)
    return new Money(result, this.currency)
  }

  /**
   * Allocate amount across n buckets, handling remainder correctly.
   * Sum of allocations always equals the original amount.
   */
  allocate(ratios: number[]): Money[] {
    const total = ratios.reduce((sum, r) => sum + r, 0)
    if (total === 0) {
      throw new Error('Ratios must sum to a positive number')
    }

    const allocations: Money[] = []
    let remainder = this.amountMinor

    for (let i = 0; i < ratios.length; i++) {
      const share = Math.floor((this.amountMinor * ratios[i]!) / total)
      allocations.push(new Money(share, this.currency))
      remainder -= share
    }

    // Distribute remainder to largest shares first
    const indices = ratios
      .map((r, i) => ({ r, i }))
      .sort((a, b) => b.r - a.r)
      .map((x) => x.i)

    for (let i = 0; i < remainder; i++) {
      const idx = indices[i % indices.length]!
      allocations[idx] = new Money(allocations[idx]!.amountMinor + 1, this.currency)
    }

    return allocations
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
    return this.amountMinor - other.amountMinor
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

  format(locale = 'en-US'): string {
    return new Intl.NumberFormat(locale, {
      style: 'currency',
      currency: this.currency,
    }).format(this.toMajor())
  }

  toJSON(): MoneyInput {
    return {
      amountMinor: this.amountMinor,
      currency: this.currency,
    }
  }

  private assertSameCurrency(other: Money): void {
    if (this.currency !== other.currency) {
      throw new Error(`Currency mismatch: ${this.currency} vs ${other.currency}`)
    }
  }
}
