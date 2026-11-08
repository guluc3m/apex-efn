import type { PriceSanityBand, PriceSanityCheck, SanityDecision } from '@trato/shared-types/sanity'

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
   */
  check(offerId: string, priceEur: number, referencePrices: number[]): PriceSanityCheck {
    const now = new Date().toISOString()

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
    const indexScore = modifiedZScore(priceEur, stats.median, stats.mad)

    // Check absolute bounds first (they override statistical bands)
    if (this.config.floorPerUnit !== undefined && priceEur < this.config.floorPerUnit) {
      return this.buildResult(offerId, priceEur, stats, indexScore, relDev, 'implausible', 'discard', [
        { code: 'none', detail: `Below absolute floor ${this.config.floorPerUnit}` },
      ])
    }

    if (this.config.ceilingPerUnit !== undefined && priceEur > this.config.ceilingPerUnit) {
      return this.buildResult(offerId, priceEur, stats, indexScore, relDev, 'implausible', 'discard', [
        { code: 'none', detail: `Above absolute ceiling ${this.config.ceilingPerUnit}` },
      ])
    }

    // Determine band from index score and relative deviation
    const band = this.determineBand(indexScore, relDev, priceEur < stats.median)
    const decision = this.bandToDecision(band)

    return this.buildResult(offerId, priceEur, stats, indexScore, relDev, band, decision, [])
  }

  private determineBand(
    indexScore: number | null,
    relDev: number,
    isCheap: boolean
  ): PriceSanityBand {
    // Apply low-side factor for cheap prices (more suspicious)
    const factor = isCheap ? this.config.lowSideFactor : 1

    // Check relative deviation bounds
    const maxDrop = this.config.maxRelativeDrop * factor
    const maxRise = this.config.maxRelativeRise

    // Cheap and more than 60% below median is at least atypical
    if (isCheap && relDev < -0.6) {
      return 'atypical'
    }

    // Outside relative bounds
    if (relDev < -maxDrop || relDev > maxRise) {
      // Check if it's extreme
      if (relDev < -maxDrop * 1.5 || relDev > maxRise * 1.5) {
        return 'implausible'
      }
      return 'atypical'
    }

    // Use index score if available
    if (indexScore !== null) {
      const absIndex = Math.abs(indexScore)
      const zOk = this.config.zOk * factor
      const zGate = this.config.zGate * factor

      if (absIndex > zGate) {
        return 'implausible'
      }
      if (absIndex > zOk) {
        return 'atypical'
      }
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
    priceEur: number,
    stats: ReturnType<typeof robustStatistics>,
    indexScore: number | null,
    relDev: number,
    band: PriceSanityBand,
    decision: SanityDecision,
    explanations: PriceSanityCheck['explanations']
  ): PriceSanityCheck {
    return {
      offerId,
      referencePriceEur: priceEur,
      median: Math.round(stats.median),
      dispersionMeasure: stats.dispersionMeasure,
      dispersionValue: stats.dispersionValue,
      sampleSize: 0, // Will be set by caller
      indexScore,
      relativeDeviation: relDev,
      band,
      decision,
      explanations,
      configVersion: this.config.configVersion,
      checkedAt: new Date().toISOString(),
    }
  }

  get configVersion(): string {
    return this.config.configVersion
  }
}
