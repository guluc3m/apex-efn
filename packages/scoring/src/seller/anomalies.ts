import type { ReviewAnomaly, RawSellerSignals } from '@trato/shared-types/seller'

import { zScore } from './statistics.js'

export interface ReviewAnomalyDetectorConfig {
  burstZThreshold: number
  fiveStarAnomalyThreshold: number
  lowVerifiedThreshold: number
  categoryFiveStarShare: number
  categoryReviewVelocityMean: number
  categoryReviewVelocityStdDev: number
}

const DEFAULT_CONFIG: ReviewAnomalyDetectorConfig = {
  burstZThreshold: 3.0,
  fiveStarAnomalyThreshold: 0.95,
  lowVerifiedThreshold: 0.2,
  categoryFiveStarShare: 0.6,
  categoryReviewVelocityMean: 10,
  categoryReviewVelocityStdDev: 5,
}

/**
 * Detect review manipulation anomalies.
 * Step 3 of seller confidence: penalties and caps (section 3.4.2).
 *
 * Any flag caps the seller band to 'low' regardless of other scores.
 * Detection is deterministic and based on structural signals, not text analysis.
 */
export function detectReviewAnomalies(
  signals: RawSellerSignals,
  config: Partial<ReviewAnomalyDetectorConfig> = {}
): ReviewAnomaly[] {
  const cfg = { ...DEFAULT_CONFIG, ...config }
  const anomalies: ReviewAnomaly[] = []
  const now = new Date().toISOString()

  // 1. Burst velocity: unusually high review rate
  if (signals.reviews12m !== undefined) {
    const monthlyRate = signals.reviews12m / 12
    const z = zScore(monthlyRate, cfg.categoryReviewVelocityMean, cfg.categoryReviewVelocityStdDev)

    if (z > cfg.burstZThreshold) {
      anomalies.push({
        type: 'burst_velocity',
        severity: z > cfg.burstZThreshold * 1.5 ? 'critical' : 'warning',
        evidence: {
          monthlyRate,
          zScore: z,
          threshold: cfg.burstZThreshold,
        },
        detectedAt: now,
      })
    }
  }

  // 2. Five-star anomaly: proportion of 5-star reviews too high
  // This requires rating distribution which we don't have in raw signals
  // For now, we check if average rating is suspiciously high with few reviews
  if (signals.ratingAvg !== undefined && signals.ratingCount !== undefined) {
    if (signals.ratingAvg >= 4.9 && signals.ratingCount < 50) {
      anomalies.push({
        type: 'five_star_anomaly',
        severity: 'warning',
        evidence: {
          ratingAvg: signals.ratingAvg,
          ratingCount: signals.ratingCount,
        },
        detectedAt: now,
      })
    }
  }

  // 3. Low verified share
  if (signals.verifiedReviewShare !== undefined) {
    if (signals.verifiedReviewShare < cfg.lowVerifiedThreshold) {
      anomalies.push({
        type: 'low_verified_share',
        severity: signals.verifiedReviewShare < 0.1 ? 'critical' : 'warning',
        evidence: {
          verifiedShare: signals.verifiedReviewShare,
          threshold: cfg.lowVerifiedThreshold,
        },
        detectedAt: now,
      })
    }
  }

  // 4. Creation correlation: reviews spike around account creation
  // Requires review timestamps which we don't have, so this is a placeholder
  // for when we have review history data

  return anomalies
}

/**
 * Check if any anomaly is critical (caps band)
 */
export function hasCriticalAnomaly(anomalies: ReviewAnomaly[]): boolean {
  return anomalies.some((a) => a.severity === 'critical')
}

/**
 * Check if any anomaly is present (affects scoring)
 */
export function hasAnyAnomaly(anomalies: ReviewAnomaly[]): boolean {
  return anomalies.length > 0
}
