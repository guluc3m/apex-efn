import type { Currency, FxRate } from '@apex/shared-types/currency'
import { FX_PIVOT_CURRENCY } from '@apex/shared-types/currency'

import { Money } from './money.js'

/**
 * Interface for FX rate providers
 */
export interface FxRateProvider {
  getRate(base: Currency, quote: Currency, asOf?: Date): Promise<FxRate | null>
  getRatesAsOf(asOf: Date): Promise<FxRate[]>
}

/**
 * FX rate record with conversion tracking
 */
export interface ConversionResult {
  money: Money
  originalMoney: Money
  rate: FxRate
  converted: boolean
}

/**
 * FX conversion utilities using EUR as pivot currency.
 * All rates are stored against EUR for triangulation.
 */
export class FxConverter {
  private readonly rates: Map<string, FxRate>
  private readonly maxAgeMs: number

  constructor(rates: FxRate[], maxAgeHours = 36) {
    this.rates = new Map()
    this.maxAgeMs = maxAgeHours * 60 * 60 * 1000

    for (const rate of rates) {
      const key = this.rateKey(rate.base, rate.quote)
      this.rates.set(key, rate)
    }
  }

  private rateKey(base: Currency, quote: Currency): string {
    return `${base}/${quote}`
  }

  /**
   * Get direct rate if available
   */
  getDirectRate(base: Currency, quote: Currency): FxRate | null {
    return this.rates.get(this.rateKey(base, quote)) ?? null
  }

  /**
   * Get rate with triangulation through EUR pivot
   */
  getRate(base: Currency, quote: Currency, now: Date): FxRate | null {
    if (base === quote) {
      return {
        base,
        quote,
        rate: 1,
        asOf: now.toISOString(),
        source: 'identity',
      }
    }

    // Try direct rate
    const direct = this.getDirectRate(base, quote)
    if (direct) {
      return this.validateFreshness(direct, now)
    }

    // Try inverse
    const inverse = this.getDirectRate(quote, base)
    if (inverse) {
      const validated = this.validateFreshness(inverse, now)
      if (!validated) return null
      return {
        base,
        quote,
        rate: 1 / inverse.rate,
        asOf: inverse.asOf,
        source: `${inverse.source} (inverted)`,
      }
    }

    // Triangulate through EUR
    if (base !== FX_PIVOT_CURRENCY && quote !== FX_PIVOT_CURRENCY) {
      const baseToPivot = this.getRate(base, FX_PIVOT_CURRENCY, now)
      const pivotToQuote = this.getRate(FX_PIVOT_CURRENCY, quote, now)

      if (baseToPivot && pivotToQuote) {
        const olderAsOf =
          Date.parse(baseToPivot.asOf) < Date.parse(pivotToQuote.asOf)
            ? baseToPivot.asOf
            : pivotToQuote.asOf
        return {
          base,
          quote,
          rate: baseToPivot.rate * pivotToQuote.rate,
          asOf: olderAsOf,
          source: `triangulated via ${FX_PIVOT_CURRENCY}`,
        }
      }
    }

    return null
  }

  /**
   * Convert money to target currency
   */
  convert(money: Money, targetCurrency: Currency, now: Date): ConversionResult | null {
    if (money.currency === targetCurrency) {
      return {
        money,
        originalMoney: money,
        rate: {
          base: money.currency,
          quote: targetCurrency,
          rate: 1,
          asOf: now.toISOString(),
          source: 'identity',
        },
        converted: false,
      }
    }

    const rate = this.getRate(money.currency, targetCurrency, now)
    if (!rate) {
      return null
    }

    const convertedMinor = Math.round(money.amountMinor * rate.rate)
    return {
      money: Money.fromMinor(convertedMinor, targetCurrency),
      originalMoney: money,
      rate,
      converted: true,
    }
  }

  /**
   * Check if rate is fresh enough
   */
  isRateFresh(rate: FxRate, now: Date): boolean {
    return now.getTime() - Date.parse(rate.asOf) < this.maxAgeMs
  }

  /**
   * Returns null if rate is stale
   */
  private validateFreshness(rate: FxRate, now: Date): FxRate | null {
    if (!this.isRateFresh(rate, now)) {
      return null
    }
    return rate
  }

  /**
   * Add or update rates
   */
  updateRates(rates: FxRate[]): void {
    for (const rate of rates) {
      const key = this.rateKey(rate.base, rate.quote)
      const existing = this.rates.get(key)

      // Only update if newer
      if (!existing || Date.parse(rate.asOf) > Date.parse(existing.asOf)) {
        this.rates.set(key, rate)
      }
    }
  }
}
