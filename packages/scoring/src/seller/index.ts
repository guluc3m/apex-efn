/**
 * Seller confidence scoring (section 3.4)
 */

export { SellerConfidenceEngine, type SellerConfidenceEngineConfig } from './engine.js'
export { normalizeSignals } from './normalize.js'
export { detectReviewAnomalies, type ReviewAnomalyDetectorConfig } from './anomalies.js'
export { wilsonLowerBound, bayesianRating } from './statistics.js'
