import type { NormalizedSellerSignals, RawSellerSignals } from '@apex/shared-types/seller'

import { bayesianRating, linearSaturation, logSaturation } from './statistics.js'

export interface NormalizationConfig {
  ageSaturationDays: number
  transactionSaturation: number
  productSaturation: number
  reviewSaturation: number
  ratingPriorWeight: number
  categoryMeanRating: number
}

const DEFAULT_CONFIG: NormalizationConfig = {
  ageSaturationDays: 730,
  transactionSaturation: 10000,
  productSaturation: 1000,
  reviewSaturation: 500,
  ratingPriorWeight: 25,
  categoryMeanRating: 4.2,
}

/**
 * Normalize raw seller signals to [0,1] range.
 * Step 1 of the seller confidence calculation (section 3.4.2).
 *
 * All transformations are deterministic and documented.
 */
export function normalizeSignals(
  raw: RawSellerSignals,
  config: Partial<NormalizationConfig> = {}
): NormalizedSellerSignals {
  const cfg = { ...DEFAULT_CONFIG, ...config }

  // Count available signals for data completeness
  const requiredSignals = [
    'accountAgeDays',
    'lifetimeTransactions',
    'publishedProductsCount',
    'ratingAvg',
    'ratingCount',
  ] as const

  const presentSignals = requiredSignals.filter((key) => raw[key] !== undefined)
  const dataCompleteness = presentSignals.length / requiredSignals.length

  // Age normalization: linear saturation
  const ageNorm = linearSaturation(raw.accountAgeDays ?? 0, cfg.ageSaturationDays)

  // Activity: months active in last 12
  const activityNorm = (raw.monthsActiveLast12 ?? 0) / 12

  // Volume: log saturation of transactions
  const volumeNorm = logSaturation(raw.lifetimeTransactions ?? 0, cfg.transactionSaturation)

  // Catalog: log saturation of products
  const catalogNorm = logSaturation(raw.publishedProductsCount ?? 0, cfg.productSaturation)

  // Rating: Bayesian adjustment
  const ratingAdjusted = bayesianRating(
    raw.ratingAvg ?? cfg.categoryMeanRating,
    raw.ratingCount ?? 0,
    cfg.categoryMeanRating,
    cfg.ratingPriorWeight
  )

  // Rating normalized to [0,1] from [0,5]
  const ratingNorm = ratingAdjusted / 5

  // Review volume: log saturation
  const reviewVolumeNorm = logSaturation(raw.reviewsTotal ?? 0, cfg.reviewSaturation)

  // Verified share: direct [0,1]
  const verifiedShareNorm = raw.verifiedReviewShare ?? 0

  // Institutional signals: weighted combination
  const institutionalFactors = [
    raw.identityVerified ? 0.3 : 0,
    raw.tradeAssurance ? 0.3 : 0,
    raw.escrowAvailable ? 0.2 : 0,
    Math.max(0, 0.2 - (raw.disputeRate ?? 0) * 4), // penalize disputes
  ]
  const institutionalNorm = institutionalFactors.reduce((a, b) => a + b, 0)

  return {
    ageNorm,
    activityNorm,
    volumeNorm,
    catalogNorm,
    ratingAdjusted,
    ratingNorm,
    reviewVolumeNorm,
    verifiedShareNorm,
    institutionalNorm,
    dataCompleteness,
  }
}
