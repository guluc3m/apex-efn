import { z } from 'zod'

import { CurrencySchema, MoneySchema } from './currency.js'

/**
 * Financial metrics from CSV import (section 3.1.1)
 */
export const FinancialMetricSchema = z.enum([
  'cash_balance',
  'credit_line_available',
  'credit_line_limit',
  'accounts_receivable',
  'accounts_payable',
  'revenue',
  'cogs',
  'fixed_costs',
  'payroll',
  'debt_service',
  'capex',
  'tax_reserve',
  'safety_buffer_pct',
  'payment_term_days',
])
export type FinancialMetric = z.infer<typeof FinancialMetricSchema>

/**
 * Single row from financial CSV
 */
export const FinancialCsvRowSchema = z.object({
  period: z.string().regex(/^\d{4}-\d{2}$/),
  metric: FinancialMetricSchema,
  valueMinor: z.number().int().optional(),
  valueBp: z.number().int().optional(),
  currency: CurrencySchema.optional(),
  notes: z.string().max(500).optional(),
})
export type FinancialCsvRow = z.infer<typeof FinancialCsvRowSchema>

/**
 * Import report for CSV validation
 */
export const ImportReportSchema = z.object({
  rowsOk: z.number().int().nonnegative(),
  rowsRejected: z.number().int().nonnegative(),
  rejections: z.array(
    z.object({
      row: z.number().int(),
      reason: z.string(),
      field: z.string().optional(),
    })
  ),
  warnings: z.array(z.string()),
  projectionEnabled: z.boolean(),
  periodsLoaded: z.number().int().nonnegative(),
  referenceDate: z.string().datetime(),
})
export type ImportReport = z.infer<typeof ImportReportSchema>

/**
 * Financial snapshot status
 */
export const FinancialSnapshotStatusSchema = z.enum(['draft', 'active', 'superseded', 'stale'])
export type FinancialSnapshotStatus = z.infer<typeof FinancialSnapshotStatusSchema>

/**
 * Financial snapshot (immutable once active)
 */
export const FinancialsSnapshotSchema = z.object({
  id: z.string(),
  tenantId: z.string(),
  status: FinancialSnapshotStatusSchema,
  csvRef: z.string(), // S3 reference
  importReport: ImportReportSchema,
  baseCurrency: CurrencySchema,
  createdAt: z.string().datetime(),
  activatedAt: z.string().datetime().nullable(),
  activatedBy: z.string().nullable(),
  supersededAt: z.string().datetime().nullable(),
})
export type FinancialsSnapshot = z.infer<typeof FinancialsSnapshotSchema>

/**
 * Budget envelope per category
 */
export const BudgetEnvelopeSchema = z.object({
  category: z.string(),
  allocated: MoneySchema,
  spent: MoneySchema,
  available: MoneySchema,
  periodStart: z.string().datetime(),
  periodEnd: z.string().datetime(),
})
export type BudgetEnvelope = z.infer<typeof BudgetEnvelopeSchema>

/**
 * Financial fit verdict (section 3.5)
 */
export const FinancialVerdictSchema = z.enum(['within_budget', 'stretch', 'out_of_budget'])
export type FinancialVerdict = z.infer<typeof FinancialVerdictSchema>

/**
 * Landed cost breakdown
 */
export const LandedCostBreakdownSchema = z.object({
  unitPriceMinor: z.number().int(),
  quantity: z.number().int().positive(),
  subtotalMinor: z.number().int(),
  shippingMinor: z.number().int(),
  insuranceMinor: z.number().int(),
  dutiesMinor: z.number().int(),
  vatMinor: z.number().int(),
  capitalCostMinor: z.number().int(),
  paymentFeesMinor: z.number().int(),
  fxCostMinor: z.number().int(),
  totalMinor: z.number().int(),
  currency: CurrencySchema,
  unitLandedCostMinor: z.number().int(),
})
export type LandedCostBreakdown = z.infer<typeof LandedCostBreakdownSchema>

/**
 * Financial fit result
 */
export const FinancialFitSchema = z.object({
  offerId: z.string(),
  landedCost: LandedCostBreakdownSchema,
  verdict: FinancialVerdictSchema,
  reasons: z.array(z.string()),
  budgetUtilizationPct: z.number().min(0),
  treasuryImpactMinor: z.number().int(),
  financialsStale: z.boolean(),
  computedAt: z.string().datetime(),
})
export type FinancialFit = z.infer<typeof FinancialFitSchema>
