/**
 * @deprecated Hand-written DTO kept only so existing imports keep compiling.
 * Use the generated types from `@apex/shared-types/contracts` (source: contracts/openapi.yaml).
 * This folder is deleted once DEV-3 and DEV-5 migrate off it (D2-01 follow-up issues).
 */
import { z } from 'zod'

import { ConvertedMoneySchema, CurrencySchema } from './currency.js'
import { PriceSanityCheckSchema } from './sanity.js'
import { SellerConfidenceSchema } from './seller.js'

/**
 * Incoterms supported
 */
export const IncotermSchema = z.enum([
  'EXW',
  'FCA',
  'FAS',
  'FOB',
  'CFR',
  'CIF',
  'CPT',
  'CIP',
  'DAP',
  'DPU',
  'DDP',
])
export type Incoterm = z.infer<typeof IncotermSchema>

/**
 * Price tier for volume discounts
 */
export const PriceTierSchema = z.object({
  minQuantity: z.number().int().positive(),
  maxQuantity: z.number().int().positive().nullable(),
  unitPriceMinor: z.number().int().nonnegative(),
  currency: CurrencySchema,
})
export type PriceTier = z.infer<typeof PriceTierSchema>

/**
 * Shipping estimate
 */
export const ShippingEstimateSchema = z.object({
  costMinor: z.number().int().nonnegative(),
  currency: CurrencySchema,
  minDays: z.number().int().nonnegative(),
  maxDays: z.number().int().nonnegative(),
  carrier: z.string().optional(),
  incoterm: IncotermSchema.optional(),
})
export type ShippingEstimate = z.infer<typeof ShippingEstimateSchema>

/**
 * Offer from a platform adapter
 */
export const OfferSchema = z.object({
  id: z.string(),
  missionId: z.string(),
  platform: z.string(),
  platformOfferId: z.string(),
  productUrl: z.string().url(),

  // Product info
  productKey: z.string(),
  title: z.string(),
  description: z.string().optional(),
  specifications: z.record(z.string()).optional(),
  certifications: z.array(z.string()).optional(),
  imageUrls: z.array(z.string().url()).optional(),

  // Seller
  sellerId: z.string(),
  sellerName: z.string(),
  sellerCountry: z.string().optional(),

  // Pricing
  unitPrice: ConvertedMoneySchema,
  moq: z.number().int().positive(),
  priceTiers: z.array(PriceTierSchema).optional(),

  // Shipping
  shipping: ShippingEstimateSchema.optional(),
  leadTimeDays: z.number().int().nonnegative().optional(),

  // Metadata
  discoveredAt: z.string().datetime(),
  expiresAt: z.string().datetime().optional(),

  // Enrichment (added after initial discovery)
  sellerConfidence: SellerConfidenceSchema.optional(),
  priceSanityCheck: PriceSanityCheckSchema.optional(),
})
export type Offer = z.infer<typeof OfferSchema>

/**
 * Offer state in the pipeline
 */
export const OfferStateSchema = z.enum([
  'discovered',
  'enriched',
  'trust_scored',
  'sanity_checked',
  'gate_pending',
  'gate_approved',
  'gate_rejected',
  'financially_checked',
  'negotiating',
  'negotiated',
  'sanity_rechecked',
  'scored',
  'awaiting_human',
  'signed',
  'approved',
  'rejected',
  'purchased',
])
export type OfferState = z.infer<typeof OfferStateSchema>
