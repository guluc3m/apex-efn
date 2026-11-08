import type {
  NormalizedSellerSignals,
  RawSellerSignals,
  SellerConfidence,
  SellerConfidenceBand,
} from '@apex/shared-types/seller'

import { detectReviewAnomalies, hasAnyAnomaly, type ReviewAnomalyDetectorConfig } from './anomalies.js'
import { normalizeSignals, type NormalizationConfig } from './normalize.js'

export interface SellerConfidenceEngineConfig {
  // Weights for each signal group (must sum to 1)
  weights: {
    age: number
    sales: number
    catalog: number
    reviews: number
    institutional: number
  }
  // Band thresholds
  bandHigh: number
  bandMedium: number
  bandLow: number
  hardBlockBelow: number
  minSignals: number
  // Model version for reproducibility
  modelVersion: string
  // Sub-configs
  normalization?: Partial<NormalizationConfig>
  anomalyDetection?: Partial<ReviewAnomalyDetectorConfig>
}

const DEFAULT_WEIGHTS = {
  age: 0.15,
  sales: 0.2,
  catalog: 0.1,
  reviews: 0.25,
  institutional: 0.3,
}

const DEFAULT_CONFIG: SellerConfidenceEngineConfig = {
  weights: DEFAULT_WEIGHTS,
  bandHigh: 75,
  bandMedium: 50,
  bandLow: 25,
  hardBlockBelow: 20,
  minSignals: 3,
  modelVersion: '1.0.0',
}

/**
 * Deterministic seller confidence scoring engine.
 * Implements section 3.4 of the spec.
 *
 * The engine is reproducible: same signals + same config = same score.
 * Model version is tracked for auditability.
 */
export class SellerConfidenceEngine {
  private readonly config: SellerConfidenceEngineConfig

  constructor(config: Partial<SellerConfidenceEngineConfig> = {}) {
    this.config = {
      ...DEFAULT_CONFIG,
      ...config,
      weights: { ...DEFAULT_WEIGHTS, ...config.weights },
    }

    // Validate weights sum to approximately 1
    const weightSum = Object.values(this.config.weights).reduce((a, b) => a + b, 0)
    if (Math.abs(weightSum - 1) > 0.001) {
      throw new Error(`Weights must sum to 1, got ${weightSum}`)
    }
  }

  /**
   * Compute seller confidence from raw signals.
   */
  compute(
    sellerId: string,
    signals: RawSellerSignals,
    snapshotId: string
  ): SellerConfidence {
    const now = new Date().toISOString()

    // Step 1: Normalize signals
    const normalized = normalizeSignals(signals, this.config.normalization)

    // Step 2: Check data completeness
    if (normalized.dataCompleteness < this.config.minSignals / 5) {
      return {
        sellerId,
        score: 0,
        band: 'insufficient_data',
        signalsNormalized: normalized,
        penalties: ['insufficient_signals'],
        flags: [],
        modelVersion: this.config.modelVersion,
        computedAt: now,
        snapshotId,
      }
    }

    // Step 3: Detect anomalies
    const anomalies = detectReviewAnomalies(signals, this.config.anomalyDetection)

    // Step 4: Calculate weighted score
    const rawScore = this.calculateWeightedScore(normalized)

    // Step 5: Apply penalties
    const penalties: string[] = []
    let score = rawScore

    // Dispute rate penalty
    if (signals.disputeRate !== undefined && signals.disputeRate > 0.05) {
      const penalty = Math.min(20, (signals.disputeRate - 0.05) * 100)
      score -= penalty
      penalties.push(`dispute_rate_penalty:-${penalty.toFixed(1)}`)
    }

    // Refund rate penalty
    if (signals.refundRate !== undefined && signals.refundRate > 0.1) {
      const penalty = Math.min(15, (signals.refundRate - 0.1) * 50)
      score -= penalty
      penalties.push(`refund_rate_penalty:-${penalty.toFixed(1)}`)
    }

    // Ensure score is in valid range
    score = Math.max(0, Math.min(100, Math.round(score)))

    // Step 6: Determine band (anomalies cap to 'low')
    const band = this.determineBand(score, hasAnyAnomaly(anomalies))

    return {
      sellerId,
      score,
      band,
      signalsNormalized: normalized,
      penalties,
      flags: anomalies,
      modelVersion: this.config.modelVersion,
      computedAt: now,
      snapshotId,
    }
  }

  private calculateWeightedScore(signals: NormalizedSellerSignals): number {
    const { weights } = this.config

    // Combine related signals into group scores
    const ageScore = signals.ageNorm * 0.7 + signals.activityNorm * 0.3
    const salesScore = signals.volumeNorm
    const catalogScore = signals.catalogNorm
    const reviewsScore =
      signals.ratingNorm * 0.4 + signals.reviewVolumeNorm * 0.3 + signals.verifiedShareNorm * 0.3
    const institutionalScore = signals.institutionalNorm

    // Weighted combination
    const score =
      weights.age * ageScore +
      weights.sales * salesScore +
      weights.catalog * catalogScore +
      weights.reviews * reviewsScore +
      weights.institutional * institutionalScore

    // Scale to 0-100
    return score * 100
  }

  private determineBand(score: number, hasAnomaly: boolean): SellerConfidenceBand {
    // Anomalies cap to 'low' regardless of score
    if (hasAnomaly && score >= this.config.bandLow) {
      return 'low'
    }

    if (score >= this.config.bandHigh) {
      return 'high'
    }
    if (score >= this.config.bandMedium) {
      return 'medium'
    }
    if (score >= this.config.bandLow) {
      return 'low'
    }
    if (score < this.config.hardBlockBelow) {
      return 'untrusted'
    }
    return 'low'
  }

  get modelVersion(): string {
    return this.config.modelVersion
  }
}
