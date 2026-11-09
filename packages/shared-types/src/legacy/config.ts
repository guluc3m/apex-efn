/**
 * @deprecated Hand-written DTO kept only so existing imports keep compiling.
 * Use the generated types from `@apex/shared-types/contracts` (source: contracts/openapi.yaml).
 * This folder is deleted once DEV-3 and DEV-5 migrate off it (D2-01 follow-up issues).
 */
import { z } from 'zod'

/**
 * Tenant configuration schema (section 7)
 * All values versionable and signed when changed
 */

export const SanityConfigSchema = z.object({
  minSample: z.number().int().positive().default(5),
  zOk: z.number().positive().default(3.5),
  zGate: z.number().positive().default(6.0),
  lowSideFactor: z.number().positive().max(1).default(0.8),
  maxRelativeRise: z.number().positive().max(1).default(0.4),
  maxRelativeDrop: z.number().positive().max(1).default(0.3),
  floorPerUnit: z.number().int().nonnegative().optional(),
  ceilingPerUnit: z.number().int().nonnegative().optional(),
  onInsufficientReference: z.enum(['gate', 'negotiate']).default('gate'),
})
export type SanityConfig = z.infer<typeof SanityConfigSchema>

export const SellerWeightsSchema = z.object({
  age: z.number().min(0).max(1).default(0.15),
  sales: z.number().min(0).max(1).default(0.2),
  catalog: z.number().min(0).max(1).default(0.1),
  reviews: z.number().min(0).max(1).default(0.25),
  institutional: z.number().min(0).max(1).default(0.3),
})
export type SellerWeights = z.infer<typeof SellerWeightsSchema>

export const SellerConfigSchema = z.object({
  weights: SellerWeightsSchema.default({}),
  ratingPriorWeight: z.number().positive().default(25),
  ageSaturationDays: z.number().int().positive().default(730),
  minSignals: z.number().int().positive().default(3),
  bandHigh: z.number().int().min(0).max(100).default(75),
  bandMedium: z.number().int().min(0).max(100).default(50),
  bandLow: z.number().int().min(0).max(100).default(25),
  hardBlockBelow: z.number().int().min(0).max(100).default(20),
  minAcceptedBand: z.enum(['high', 'medium', 'low']).default('medium'),
  reviewBurstZ: z.number().positive().default(3.0),
  maxDisputeRate: z.number().min(0).max(1).default(0.05),
  snapshotMaxAgeDays: z.number().int().positive().default(30),
  escalateCheapLowConfidence: z.boolean().default(true),
})
export type SellerConfig = z.infer<typeof SellerConfigSchema>

export const FinanceConfigSchema = z.object({
  safetyBufferPct: z.number().min(0).max(100).default(15),
  staleAfterDays: z.number().int().positive().default(45),
})
export type FinanceConfig = z.infer<typeof FinanceConfigSchema>

export const FxConfigSchema = z.object({
  maxAgeHours: z.number().int().positive().default(36),
})
export type FxConfig = z.infer<typeof FxConfigSchema>

export const NegotiationConfigSchema = z.object({
  targetDiscount: z.number().min(0).max(1).optional(),
  maxDiscount: z.number().min(0).max(1).optional(),
  maxRounds: z.number().int().positive().default(6),
})
export type NegotiationConfig = z.infer<typeof NegotiationConfigSchema>

export const GateConfigSchema = z.object({
  slaHours: z.number().int().positive().default(24),
  maxRenegotiations: z.number().int().nonnegative().default(1),
})
export type GateConfig = z.infer<typeof GateConfigSchema>

export const ApprovalConfigSchema = z.object({
  threshold: z.number().int().nonnegative().optional(),
  dualControlAbove: z.number().int().nonnegative().optional(),
})
export type ApprovalConfig = z.infer<typeof ApprovalConfigSchema>

export const SigningConfigSchema = z.object({
  sessionMinutes: z.number().int().positive().default(15),
  maxDecisionsPerSession: z.number().int().positive().default(10),
  highValueReauthAbove: z.number().int().nonnegative().optional(),
})
export type SigningConfig = z.infer<typeof SigningConfigSchema>

export const TenantConfigSchema = z.object({
  version: z.string(),
  tenantId: z.string(),
  sanity: SanityConfigSchema.default({}),
  seller: SellerConfigSchema.default({}),
  finance: FinanceConfigSchema.default({}),
  fx: FxConfigSchema.default({}),
  negotiation: NegotiationConfigSchema.default({}),
  gate: GateConfigSchema.default({}),
  approval: ApprovalConfigSchema.default({}),
  signing: SigningConfigSchema.default({}),
  updatedAt: z.string().datetime(),
  updatedBy: z.string(),
})
export type TenantConfig = z.infer<typeof TenantConfigSchema>

/**
 * Category-specific overrides
 */
export const CategoryConfigOverrideSchema = z.object({
  tenantId: z.string(),
  category: z.string(),
  sanity: SanityConfigSchema.partial().optional(),
  seller: SellerConfigSchema.partial().optional(),
  negotiation: NegotiationConfigSchema.partial().optional(),
  version: z.string(),
  updatedAt: z.string().datetime(),
  updatedBy: z.string(),
})
export type CategoryConfigOverride = z.infer<typeof CategoryConfigOverrideSchema>
