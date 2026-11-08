/**
 * Robust statistics for price sanity checking.
 * Uses median and MAD instead of mean and stddev to resist outliers.
 */

export interface RobustStats {
  median: number
  mad: number
  iqr: number
  dispersionMeasure: 'mad' | 'iqr' | 'relative'
  dispersionValue: number
}

/**
 * Calculate median of sorted array
 */
export function median(values: number[]): number {
  if (values.length === 0) {
    throw new Error('Cannot calculate median of empty array')
  }

  const sorted = [...values].sort((a, b) => a - b)
  const mid = Math.floor(sorted.length / 2)

  if (sorted.length % 2 === 0) {
    return (sorted[mid - 1]! + sorted[mid]!) / 2
  }
  return sorted[mid]!
}

/**
 * Calculate Median Absolute Deviation (MAD)
 * More robust than standard deviation against outliers
 */
export function mad(values: number[]): number {
  if (values.length === 0) {
    throw new Error('Cannot calculate MAD of empty array')
  }

  const med = median(values)
  const deviations = values.map((v) => Math.abs(v - med))
  return median(deviations)
}

/**
 * Calculate Interquartile Range (IQR)
 * Fallback when MAD is 0
 */
export function iqr(values: number[]): number {
  if (values.length < 4) {
    return 0
  }

  const sorted = [...values].sort((a, b) => a - b)
  const q1Index = Math.floor(sorted.length * 0.25)
  const q3Index = Math.floor(sorted.length * 0.75)

  return sorted[q3Index]! - sorted[q1Index]!
}

/**
 * Calculate robust dispersion statistic (MAD, falling back to IQR)
 */
export function robustStatistics(prices: number[]): RobustStats {
  if (prices.length === 0) {
    throw new Error('Cannot calculate statistics of empty array')
  }

  const med = median(prices)
  const madValue = mad(prices)

  // If MAD is 0 (identical prices), try IQR
  if (madValue === 0) {
    const iqrValue = iqr(prices)
    if (iqrValue === 0) {
      // All prices identical, use relative deviation
      return {
        median: med,
        mad: 0,
        iqr: 0,
        dispersionMeasure: 'relative',
        dispersionValue: 0,
      }
    }
    return {
      median: med,
      mad: 0,
      iqr: iqrValue,
      dispersionMeasure: 'iqr',
      dispersionValue: iqrValue,
    }
  }

  return {
    median: med,
    mad: madValue,
    iqr: iqr(prices),
    dispersionMeasure: 'mad',
    dispersionValue: madValue,
  }
}

/**
 * Calculate modified z-score using MAD
 * Formula: 0.6745 * (x - median) / MAD
 * The constant 0.6745 makes it comparable to standard z-score for normal distributions
 */
export function modifiedZScore(value: number, median: number, mad: number): number | null {
  if (mad === 0) {
    return null // Cannot calculate with zero MAD
  }
  return (0.6745 * (value - median)) / mad
}

/**
 * Calculate relative deviation from median
 */
export function relativeDeviation(value: number, median: number): number {
  if (median === 0) {
    return value === 0 ? 0 : Infinity
  }
  return (value - median) / median
}
