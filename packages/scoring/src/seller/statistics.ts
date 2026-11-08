/**
 * Statistical utilities for seller scoring
 */

/**
 * Wilson lower bound for binomial proportion confidence interval.
 * Returns the lower bound at 95% confidence.
 * Used for verified review share to reward evidence over small samples.
 *
 * @param positive Number of positive outcomes (e.g., verified reviews)
 * @param total Total number of observations
 * @param confidence Confidence level (default 0.95)
 */
export function wilsonLowerBound(positive: number, total: number, confidence = 0.95): number {
  if (total === 0) return 0

  // Z-score for confidence level (1.96 for 95%)
  const z = confidence === 0.95 ? 1.96 : 1.645 // simplified, use 1.645 for 90%
  const phat = positive / total

  const numerator = phat + (z * z) / (2 * total) - z * Math.sqrt((phat * (1 - phat) + (z * z) / (4 * total)) / total)
  const denominator = 1 + (z * z) / total

  return Math.max(0, numerator / denominator)
}

/**
 * Bayesian rating adjustment using shrinkage toward category mean.
 * Prevents a single 5-star review from outranking hundreds of 4.8 reviews.
 *
 * Formula: (C * m + rating * count) / (C + count)
 * where C is the prior weight and m is the category mean
 *
 * @param rating Current average rating
 * @param count Number of ratings
 * @param categoryMean Mean rating in the category
 * @param priorWeight Weight of the prior (C parameter, default 25)
 */
export function bayesianRating(
  rating: number,
  count: number,
  categoryMean: number,
  priorWeight = 25
): number {
  return (priorWeight * categoryMean + rating * count) / (priorWeight + count)
}

/**
 * Logarithmic saturation function for counts.
 * Maps unbounded counts to [0, 1] with diminishing returns.
 *
 * f(x) = log10(1 + x) / log10(1 + saturation)
 *
 * @param value Count value
 * @param saturation Value at which output reaches 1.0
 */
export function logSaturation(value: number, saturation: number): number {
  if (value <= 0) return 0
  if (saturation <= 0) throw new Error('Saturation must be positive')

  const result = Math.log10(1 + value) / Math.log10(1 + saturation)
  return Math.min(1, result)
}

/**
 * Linear saturation with ceiling.
 *
 * @param value Input value
 * @param saturation Value at which output reaches 1.0
 */
export function linearSaturation(value: number, saturation: number): number {
  if (value <= 0) return 0
  if (saturation <= 0) throw new Error('Saturation must be positive')

  return Math.min(1, value / saturation)
}

/**
 * Z-score calculation for anomaly detection
 */
export function zScore(value: number, mean: number, stdDev: number): number {
  if (stdDev === 0) return 0
  return (value - mean) / stdDev
}
