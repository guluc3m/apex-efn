import { z } from 'zod'

/**
 * Price sanity bands per section 3.3.3
 */
export const PriceSanityBandSchema = z.enum([
  'normal',
  'atypical',
  'implausible',
  'insufficient_reference',
])
export type PriceSanityBand = z.infer<typeof PriceSanityBandSchema>

/**
 * Decision from sanity check
 */
export const SanityDecisionSchema = z.enum(['negotiate', 'human_gate', 'discard'])
export type SanityDecision = z.infer<typeof SanityDecisionSchema>

/**
 * Explanation codes for price anomalies (enum, not free text)
 */
export const PriceExplanationCodeSchema = z.enum([
  'volume_tier_difference',
  'moq_difference',
  'incoterm_difference',
  'quality_grade_difference',
  'specification_difference',
  'seasonal_pricing',
  'clearance_sale',
  'new_seller_promotion',
  'bulk_discount',
  'none',
])
export type PriceExplanationCode = z.infer<typeof PriceExplanationCodeSchema>

/**
 * Dispersion measure used
 */
export const DispersionMeasureSchema = z.enum(['mad', 'iqr', 'relative'])
export type DispersionMeasure = z.infer<typeof DispersionMeasureSchema>

/**
 * Price sanity check result (section 3.3.4)
 */
export const PriceSanityCheckSchema = z.object({
  offerId: z.string(),
  referencePriceEur: z.number().int(),
  median: z.number().int(),
  dispersionMeasure: DispersionMeasureSchema,
  dispersionValue: z.number(),
  sampleSize: z.number().int().nonnegative(),
  indexScore: z.number().nullable(),
  relativeDeviation: z.number(),
  band: PriceSanityBandSchema,
  decision: SanityDecisionSchema,
  explanations: z.array(
    z.object({
      code: PriceExplanationCodeSchema,
      detail: z.string().optional(),
    })
  ),
  configVersion: z.string(),
  checkedAt: z.string().datetime(),
})
export type PriceSanityCheck = z.infer<typeof PriceSanityCheckSchema>

/**
 * Price history entry for reference calculations
 */
export const PriceHistorySchema = z.object({
  productKey: z.string(),
  sellerId: z.string(),
  landedUnitCostEur: z.number().int(),
  date: z.string().datetime(),
  missionId: z.string().optional(),
})
export type PriceHistory = z.infer<typeof PriceHistorySchema>
