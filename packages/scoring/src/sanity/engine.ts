import type { PriceSanityBand, PriceSanityCheck, SanityDecision } from '@apex/shared-types/sanity'

import { modifiedZScore, relativeDeviation, robustStatistics } from './statistics.js'

export interface PriceSanityEngineConfig {
  minSample: number
  zOk: number
  zGate: number
  lowSideFactor: number
  maxRelativeRise: number
  maxRelativeDrop: number
  floorPerUnit?: number
  ceilingPerUnit?: number
  onInsufficientReference: 'gate' | 'negotiate'
  configVersion: string
}

const DEFAULT_CONFIG: PriceSanityEngineConfig = {
  minSample: 5,
  zOk: 3.5,
  zGate: 6.0,
  lowSideFactor: 0.8,
  maxRelativeRise: 0.4,
  maxRelativeDrop: 0.3,
  onInsufficientReference: 'gate',
  configVersion: '1.0.0',
}

const HARD_MAX_RELATIVE_DROP = 0.6

/**
 * Price sanity checking engine.
 * Implements section 3.3 of the spec.
 *
 * Uses robust statistics (MAD) to detect price outliers.
 * Asymmetric thresholds: cheap prices are more suspicious than expensive ones.
 */
export class PriceSanityEngine {
  private readonly config: PriceSanityEngineConfig

  constructor(config: Partial<PriceSanityEngineConfig> = {}) {
    this.config = { ...DEFAULT_CONFIG, ...config }
  }

  /**
   * Check if a price is sane compared to reference prices.
   *
   * @param offerId Offer being checked
   * @param priceEur Price in EUR minor units
   * @param referencePrices Array of reference prices in EUR minor units
   * @param now ISO-8601 timestamp from the injected clock (ADR-300)
   */
  check(
    offerId: string,
    priceEur: number,
    referencePrices: number[],
    now: string
  ): PriceSanityCheck {
    // Insufficient reference data
    if (referencePrices.length < this.config.minSample) {
      return {
        offerId,
        referencePriceEur: 0,
        median: 0,
        dispersionMeasure: 'mad',
        dispersionValue: 0,
        sampleSize: referencePrices.length,
        indexScore: null,
        relativeDeviation: 0,
        band: 'insufficient_reference',
        decision: this.config.onInsufficientReference === 'gate' ? 'human_gate' : 'negotiate',
        explanations: [
          {
            code: 'none',
            detail: `Sample size ${referencePrices.length} < required ${this.config.minSample}`,
          },
        ],
        configVersion: this.config.configVersion,
        checkedAt: now,
      }
    }

    // Calculate robust statistics
    const stats = robustStatistics(referencePrices)
    const relDev = relativeDeviation(priceEur, stats.median)
    // dispersionValue is MAD, or IQR when MAD is 0, or 0 (no index) when both are
    const indexScore = modifiedZScore(priceEur, stats.median, stats.dispersionValue)
    const sampleSize = referencePrices.length

    // Check absolute bounds first (they override statistical bands)
    if (this.config.floorPerUnit !== undefined && priceEur < this.config.floorPerUnit) {
      return this.buildResult(
        offerId,
        sampleSize,
        stats,
        indexScore,
        relDev,
        'implausible',
        'discard',
        [{ code: 'none', detail: `Below absolute floor ${this.config.floorPerUnit}` }],
        now
      )
    }

    if (this.config.ceilingPerUnit !== undefined && priceEur > this.config.ceilingPerUnit) {
      return this.buildResult(
        offerId,
        sampleSize,
        stats,
        indexScore,
        relDev,
        'implausible',
        'discard',
        [{ code: 'none', detail: `Above absolute ceiling ${this.config.ceilingPerUnit}` }],
        now
      )
    }

    // Determine band from index score and relative deviation
    const band = this.determineBand(indexScore, relDev, priceEur < stats.median)
    const decision = this.bandToDecision(band)

    return this.buildResult(offerId, sampleSize, stats, indexScore, relDev, band, decision, [], now)
  }

  private determineBand(
    indexScore: number | null,
    relDev: number,
    isCheap: boolean
  ): PriceSanityBand {
    // Apply low-side factor for cheap prices (more suspicious)
    const factor = isCheap ? this.config.lowSideFactor : 1

    // Only the index (or the absolute bounds, checked earlier) can make a price implausible
    if (indexScore !== null) {
      const absIndex = Math.abs(indexScore)

      if (absIndex > this.config.zGate * factor) {
        return 'implausible'
      }
      if (absIndex > this.config.zOk * factor) {
        return 'atypical'
      }
    }

    // More than 60% below the median is at least atypical, whatever the configured drop
    const maxDrop = Math.min(this.config.maxRelativeDrop * factor, HARD_MAX_RELATIVE_DROP)
    if (relDev < -maxDrop || relDev > this.config.maxRelativeRise) {
      return 'atypical'
    }

    return 'normal'
  }

  private bandToDecision(band: PriceSanityBand): SanityDecision {
    switch (band) {
      case 'normal':
        return 'negotiate'
      case 'atypical':
      case 'insufficient_reference':
        return 'human_gate'
      case 'implausible':
        return 'discard'
    }
  }

  private buildResult(
    offerId: string,
    sampleSize: number,
    stats: ReturnType<typeof robustStatistics>,
    indexScore: number | null,
    relDev: number,
    band: PriceSanityBand,
    decision: SanityDecision,
    explanations: PriceSanityCheck['explanations'],
    now: string
  ): PriceSanityCheck {
    return {
      offerId,
      referencePriceEur: Math.round(stats.median),
      median: Math.round(stats.median),
      dispersionMeasure: stats.dispersionMeasure,
      dispersionValue: stats.dispersionValue,
      sampleSize,
      indexScore,
      relativeDeviation: relDev,
      band,
      decision,
      explanations,
      configVersion: this.config.configVersion,
      checkedAt: now,
    }
  }

  get configVersion(): string {
    return this.config.configVersion
  }
}
