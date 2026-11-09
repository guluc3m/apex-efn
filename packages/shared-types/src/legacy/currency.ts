/**
 * @deprecated Hand-written DTO kept only so existing imports keep compiling.
 * Use the generated types from `@apex/shared-types/contracts` (source: contracts/openapi.yaml).
 * This folder is deleted once DEV-3 and DEV-5 migrate off it (D2-01 follow-up issues).
 */
import { z } from 'zod'

/**
 * Supported currencies - closed enum per spec section 3.5.1
 * NO OTHER CURRENCIES ARE SUPPORTED
 */
export const CurrencySchema = z.enum(['EUR', 'USD', 'CNY'])
export type Currency = z.infer<typeof CurrencySchema>

/**
 * Money representation with integer minor units (cents/fen)
 * NEVER use floats for money
 */
export const MoneySchema = z.object({
  amountMinor: z.number().int(),
  currency: CurrencySchema,
})
export type Money = z.infer<typeof MoneySchema>

/**
 * Money with original value tracking for FX conversions
 */
export const ConvertedMoneySchema = MoneySchema.extend({
  originalAmountMinor: z.number().int().optional(),
  originalCurrency: CurrencySchema.optional(),
  fxRate: z.number().positive().optional(),
  fxAsOf: z.string().datetime().optional(),
  fxSource: z.string().optional(),
  converted: z.boolean().default(false),
})
export type ConvertedMoney = z.infer<typeof ConvertedMoneySchema>

/**
 * FX Rate record
 */
export const FxRateSchema = z.object({
  base: CurrencySchema,
  quote: CurrencySchema,
  rate: z.number().positive(),
  asOf: z.string().datetime(),
  source: z.string(),
})
export type FxRate = z.infer<typeof FxRateSchema>

/**
 * Minor unit multipliers by currency
 */
export const CURRENCY_MINOR_UNITS: Record<Currency, number> = {
  EUR: 100,
  USD: 100,
  CNY: 100, // fen
} as const

/**
 * FX pivot currency per spec
 */
export const FX_PIVOT_CURRENCY: Currency = 'EUR'
