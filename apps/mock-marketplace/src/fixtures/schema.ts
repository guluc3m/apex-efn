import { z } from 'zod'

/**
 * Canonical fixture model of the mock marketplace. Each platform renders it in its own wire format
 * (mock-a: JSON API, mock-b: HTML, mock-c: API-first with a messaging endpoint), so adapters have real
 * mapping work to do.
 * Currencies are deliberately NOT restricted to EUR/USD/CNY: the mock must be able to serve offers and
 * quotes that the platform rejects (spec 3.5.1, criterion 24).
 */

export const PLATFORM_IDS = ['mock-a', 'mock-b', 'mock-c'] as const
export const PlatformIdSchema = z.enum(PLATFORM_IDS)
export type PlatformId = z.infer<typeof PlatformIdSchema>

export const PERSONA_IDS = [
  'cooperative',
  'aggressive',
  'evasive',
  'off_platform',
  'sensitive_data',
  'lowball',
  'chinese',
  'truncated',
  'unsupported_currency',
  'tough',
] as const
export const PersonaIdSchema = z.enum(PERSONA_IDS)
export type PersonaId = z.infer<typeof PersonaIdSchema>

export const SELLER_PROFILES = [
  'standard',
  'solid_veteran',
  'single_perfect_review',
  'manipulated_reviews',
  'insufficient_data',
  'high_disputes',
] as const
export const SellerProfileSchema = z.enum(SELLER_PROFILES)
export type SellerProfile = z.infer<typeof SellerProfileSchema>

const isoDate = z.string().regex(/^\d{4}-\d{2}-\d{2}$/, 'expected YYYY-MM-DD')
const share = z.number().min(0).max(1)
const count = z.number().int().nonnegative()
const minor = z.number().int().nonnegative()
const currencyCode = z.string().regex(/^[A-Z]{3}$/, 'expected ISO 4217 code')

/**
 * Raw signals as the platform exposes them. Every field is optional: a missing field means the platform
 * does not show it for this seller (insufficient-data sellers omit most of them).
 */
export const SellerSignalsSchema = z
  .object({
    memberSince: isoDate,
    firstSaleDate: isoDate,
    monthsActiveLast12: z.number().int().min(0).max(12),
    lifetimeTransactions: count,
    transactions12m: count,
    gmv12mMinor: minor,
    gmvCurrency: currencyCode,
    repeatBuyerShare: share,
    publishedProductsCount: count,
    catalogChurn30d: share,
    specCompletenessAvg: share,
    reviewsTotal: count,
    reviews12m: count,
    ratingAvg: z.number().min(1).max(5),
    ratingCount: count,
    verifiedReviewShare: share,
    responseRate: share,
    identityVerified: z.boolean(),
    tradeAssurance: z.boolean(),
    escrowAvailable: z.boolean(),
    disputeRate: share,
    refundRate: share,
  })
  .partial()
  .strict()
export type SellerSignals = z.infer<typeof SellerSignalsSchema>

export const ReviewSchema = z
  .object({
    id: z.string().min(1),
    rating: z.number().int().min(1).max(5),
    text: z.string(),
    date: isoDate,
    verified: z.boolean(),
  })
  .strict()
export type Review = z.infer<typeof ReviewSchema>

export const SellerSchema = z
  .object({
    id: z.string().regex(/^[a-z0-9-]+$/),
    platform: PlatformIdSchema,
    name: z.string().min(1),
    country: z
      .string()
      .regex(/^[A-Z]{2}$/)
      .nullable(),
    profile: SellerProfileSchema,
    persona: PersonaIdSchema,
    signals: SellerSignalsSchema,
    reviews: z.array(ReviewSchema),
  })
  .strict()
export type Seller = z.infer<typeof SellerSchema>

export const PriceTierSchema = z
  .object({
    minQuantity: z.number().int().positive(),
    maxQuantity: z.number().int().positive().nullable(),
    unitPriceMinor: minor,
  })
  .strict()
export type PriceTier = z.infer<typeof PriceTierSchema>

export const PRODUCT_TAGS = ['outlier_low', 'outlier_high', 'unsupported_currency'] as const

export const ProductSchema = z
  .object({
    id: z.string().regex(/^[a-z0-9-]+$/),
    platform: PlatformIdSchema,
    sellerId: z.string().min(1),
    productKey: z.string().regex(/^[a-z0-9-]+$/),
    title: z.string().min(1),
    description: z.string(),
    specifications: z.record(z.string(), z.string()),
    certifications: z.array(z.string()),
    imageUrls: z.array(z.string()),
    unitPriceMinor: minor,
    currency: currencyCode,
    moq: z.number().int().positive(),
    priceTiers: z.array(PriceTierSchema),
    shipping: z
      .object({
        costMinor: minor,
        minDays: z.number().int().nonnegative(),
        maxDays: z.number().int().nonnegative(),
      })
      .strict()
      .nullable(),
    incoterm: z.string().nullable(),
    leadTimeDays: z.number().int().nonnegative().nullable(),
    tags: z.array(z.enum(PRODUCT_TAGS)).default([]),
  })
  .strict()
export type Product = z.infer<typeof ProductSchema>

export const SellersFileSchema = z.object({ sellers: z.array(SellerSchema) }).strict()
export const ProductsFileSchema = z.object({ products: z.array(ProductSchema) }).strict()

export interface Catalog {
  sellers: readonly Seller[]
  products: readonly Product[]
}
