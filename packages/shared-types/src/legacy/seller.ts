/**
 * @deprecated Hand-written DTO kept only so existing imports keep compiling.
 * Use the generated types from `@apex/shared-types/contracts` (source: contracts/openapi.yaml).
 * This folder is deleted once DEV-3 and DEV-5 migrate off it (D2-01 follow-up issues).
 */
import { z } from 'zod'

/**
 * Raw seller signals from platform adapters (section 3.4.1)
 */
export const RawSellerSignalsSchema = z.object({
  // Antigüedad
  accountAgeDays: z.number().int().nonnegative().optional(),
  firstSaleDate: z.string().datetime().optional(),
  monthsActiveLast12: z.number().int().min(0).max(12).optional(),

  // Ventas
  lifetimeTransactions: z.number().int().nonnegative().optional(),
  transactions12m: z.number().int().nonnegative().optional(),
  gmv12m: z.number().nonnegative().optional(),
  repeatBuyerShare: z.number().min(0).max(1).optional(),

  // Catálogo
  publishedProductsCount: z.number().int().nonnegative().optional(),
  catalogChurn30d: z.number().min(0).max(1).optional(),
  specCompletenessAvg: z.number().min(0).max(1).optional(),

  // Reseñas
  reviewsTotal: z.number().int().nonnegative().optional(),
  reviews12m: z.number().int().nonnegative().optional(),
  ratingAvg: z.number().min(0).max(5).optional(),
  ratingCount: z.number().int().nonnegative().optional(),
  verifiedReviewShare: z.number().min(0).max(1).optional(),
  responseRate: z.number().min(0).max(1).optional(),

  // Garantía institucional
  identityVerified: z.boolean().optional(),
  tradeAssurance: z.boolean().optional(),
  escrowAvailable: z.boolean().optional(),
  disputeRate: z.number().min(0).max(1).optional(),
  refundRate: z.number().min(0).max(1).optional(),

  // Metadata
  capturedAt: z.string().datetime(),
  platform: z.string(),
  platformSellerId: z.string(),
})
export type RawSellerSignals = z.infer<typeof RawSellerSignalsSchema>

/**
 * Normalized seller signals [0,1] for scoring
 */
export const NormalizedSellerSignalsSchema = z.object({
  ageNorm: z.number().min(0).max(1),
  activityNorm: z.number().min(0).max(1),
  volumeNorm: z.number().min(0).max(1),
  catalogNorm: z.number().min(0).max(1),
  ratingAdjusted: z.number().min(0).max(5),
  ratingNorm: z.number().min(0).max(1),
  reviewVolumeNorm: z.number().min(0).max(1),
  verifiedShareNorm: z.number().min(0).max(1),
  institutionalNorm: z.number().min(0).max(1),
  dataCompleteness: z.number().min(0).max(1),
})
export type NormalizedSellerSignals = z.infer<typeof NormalizedSellerSignalsSchema>

/**
 * Confidence bands per section 3.4.2
 */
export const SellerConfidenceBandSchema = z.enum([
  'high',
  'medium',
  'low',
  'untrusted',
  'insufficient_data',
])
export type SellerConfidenceBand = z.infer<typeof SellerConfidenceBandSchema>

/**
 * Review anomaly types for manipulation detection
 */
export const ReviewAnomalyTypeSchema = z.enum([
  'burst_velocity',
  'five_star_anomaly',
  'low_verified_share',
  'duplicate_text',
  'creation_correlation',
])
export type ReviewAnomalyType = z.infer<typeof ReviewAnomalyTypeSchema>

export const ReviewAnomalySchema = z.object({
  type: ReviewAnomalyTypeSchema,
  severity: z.enum(['warning', 'critical']),
  evidence: z.record(z.unknown()),
  detectedAt: z.string().datetime(),
})
export type ReviewAnomaly = z.infer<typeof ReviewAnomalySchema>

/**
 * Seller confidence result (section 3.4)
 */
export const SellerConfidenceSchema = z.object({
  sellerId: z.string(),
  score: z.number().int().min(0).max(100),
  band: SellerConfidenceBandSchema,
  signalsNormalized: NormalizedSellerSignalsSchema,
  penalties: z.array(z.string()),
  flags: z.array(ReviewAnomalySchema),
  modelVersion: z.string(),
  computedAt: z.string().datetime(),
  snapshotId: z.string(),
})
export type SellerConfidence = z.infer<typeof SellerConfidenceSchema>

/**
 * Seller signal snapshot (immutable, for reproducibility)
 */
export const SellerSignalSnapshotSchema = z.object({
  id: z.string(),
  sellerId: z.string(),
  signals: RawSellerSignalsSchema,
  capturedAt: z.string().datetime(),
})
export type SellerSignalSnapshot = z.infer<typeof SellerSignalSnapshotSchema>
